from __future__ import annotations

import logging
from collections.abc import Callable

from iris.agency.bus import InternalBus, PlanDecided
from iris.agency.execution.context import ContextManager
from iris.agency.execution.monitor import OutputMonitor
from iris.agency.execution.pipeline import LLMPipeline
from iris.event.event_bus import EventBus
from iris.event.event_types import OutputRequest
from iris.memory.hippocampal.manager import HippocampalManager

logger = logging.getLogger(__name__)


class ExecutionManager:
    def __init__(
        self,
        internal_bus: InternalBus,
        event_bus: EventBus,
        llm_pipeline: LLMPipeline,
        context_manager: ContextManager | None = None,
        context_window: int = 0,
        hippocampal: HippocampalManager | None = None,
        monitor: OutputMonitor | None = None,
        session_roles_getter: Callable[[], str] | None = None,
    ) -> None:
        self._bus = internal_bus
        self._event_bus = event_bus
        self._pipeline = llm_pipeline
        self._context_mgr = context_manager
        self._context_window = context_window
        self._hippocampal = hippocampal
        self._monitor = monitor
        self._session_roles_getter = session_roles_getter
        self._messages: list[dict] = []
        self._msg_count_since_reflect = 0
        self._bus.subscribe("PlanDecided", self._on_plan)

    def _on_plan(self, event: PlanDecided) -> None:
        plan = event.plan
        action = plan.get("action")
        if action == "respond":
            self._execute_respond(plan)
        elif action == "proactive":
            self._execute_proactive(plan)
        else:
            logger.debug("ExecutionManager: unhandled action=%s", action)

    def _execute_respond(self, plan: dict) -> None:
        session_id = plan.get("session_id", "")
        content = plan.get("content", "")

        self._messages.append({"role": "user", "content": content})

        if self._session_roles_getter:
            self._pipeline.set_session_roles_summary(self._session_roles_getter())

        self._event_bus.publish(
            OutputRequest(
                session_id=session_id,
                message_type="stream",
                content="",
                state="thinking",
            )
        )

        try:
            response_text = self._pipeline.iterate_with_tools(
                self._messages,
                on_token=lambda delta: self._event_bus.publish(
                    OutputRequest(
                        session_id=session_id,
                        message_type="stream",
                        content=delta,
                        state="speaking",
                    )
                ),
            )
        except Exception as e:
            response_text = f"[Error: {e}]"
            logger.exception("LLM call failed")

        self._messages.append({"role": "assistant", "content": response_text})
        self._msg_count_since_reflect += 1
        self._msg_count_since_reflect = (
            self._hippocampal.maybe_run(self._messages, self._msg_count_since_reflect)
            if self._hippocampal
            else self._msg_count_since_reflect
        )

        if self._context_mgr:
            self._context_mgr.check_and_summarize(self._messages, self._context_window)

        if self._monitor:
            self._monitor.record_output()

        self._event_bus.publish(
            OutputRequest(
                session_id=session_id,
                message_type="stream",
                content="",
                state="done",
            )
        )
        self._event_bus.publish(
            OutputRequest(
                session_id=session_id,
                message_type="response",
                content=response_text,
            )
        )

    def compact_context(self) -> str:
        if self._context_mgr is None:
            return "Context manager not available"
        if len(self._messages) < 2:
            return "Not enough messages to compact"
        summary = self._context_mgr.compact(self._messages)
        keep = 6
        self._messages = [{"role": "system", "content": f"## Session Summary\n{summary}"}] + self._messages[-keep:]
        return f"Compacted: {len(summary)} chars summary, kept last {keep} messages"

    def _execute_proactive(self, plan: dict) -> None:
        context_hint = plan.get("context_hint", "")
        content = self._pipeline.generate_proactive(context_hint=context_hint)

        self._event_bus.publish(
            OutputRequest(
                session_id="",
                message_type="proactive",
                content=content,
            )
        )

        if self._monitor:
            self._monitor.record_output()

        logger.info("Proactive speech: %s", content)
