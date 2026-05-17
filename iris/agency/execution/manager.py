from __future__ import annotations

import logging
from collections.abc import Callable

from iris.event.event_bus import EventBus
from iris.event.event import OutputRequest
from iris.agency.bus import InternalBus, PlanDecided
from iris.agency.execution.pipeline import LLMPipeline

logger = logging.getLogger(__name__)


class ExecutionManager:
    def __init__(
        self,
        internal_bus: InternalBus,
        event_bus: EventBus,
        llm_pipeline: LLMPipeline,
        session_roles_getter: Callable[[], str] | None = None,
    ) -> None:
        self._bus = internal_bus
        self._event_bus = event_bus
        self._pipeline = llm_pipeline
        self._session_roles_getter = session_roles_getter
        self._bus.subscribe("PlanDecided", self._on_plan)

    def _on_plan(self, event: PlanDecided) -> None:
        plan = event.plan
        action = plan.get("action")
        if action == "respond":
            self._execute_respond(plan)
        else:
            logger.debug("ExecutionManager: unhandled action=%s", action)

    def _execute_respond(self, plan: dict) -> None:
        session_id = plan.get("session_id", "")
        content = plan.get("content", "")
        messages: list[dict] = [{"role": "user", "content": content}]

        if self._session_roles_getter:
            self._pipeline.set_session_roles_summary(self._session_roles_getter())

        self._event_bus.publish(OutputRequest(
            session_id=session_id,
            message_type="stream",
            content="",
            state="thinking",
        ))

        try:
            response_text = self._pipeline.iterate_with_tools(
                messages,
                on_token=lambda delta: self._event_bus.publish(OutputRequest(
                    session_id=session_id,
                    message_type="stream",
                    content=delta,
                    state="speaking",
                )),
            )
        except Exception as e:
            response_text = f"[Error: {e}]"
            logger.exception("LLM call failed")

        self._event_bus.publish(OutputRequest(
            session_id=session_id,
            message_type="stream",
            content="",
            state="done",
        ))
        self._event_bus.publish(OutputRequest(
            session_id=session_id,
            message_type="response",
            content=response_text,
        ))
