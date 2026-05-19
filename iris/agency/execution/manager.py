from __future__ import annotations

from collections.abc import Callable
import logging
import threading

from iris.agency.bus import InternalBus, PlanDecided
from iris.agency.execution.inhibition import InhibitionController
from iris.agency.execution.monitor import OutputMonitor
from iris.agency.execution.pipeline import LLMPipeline
from iris.event.event_bus import EventBus
from iris.event.event_types import MessageEvent
from iris.io.models import StreamState
from iris.kernel.config import ModelConfig
from iris.llm.context_window import LLMContextWindowManager
from iris.memory.hippocampal.manager import HippocampalManager
from iris.memory.manager import MemoryManager

logger = logging.getLogger(__name__)


class ExecutionManager:
    def __init__(
        self,
        internal_bus: InternalBus,
        event_bus: EventBus,
        llm_pipeline: LLMPipeline,
        context_window_mgr: LLMContextWindowManager | None = None,
        context_window: int = 0,
        model_config: ModelConfig | None = None,
        hippocampal: HippocampalManager | None = None,
        monitor: OutputMonitor | None = None,
        inhibition: InhibitionController | None = None,
        session_roles_getter: Callable[[], str] | None = None,
        memory: MemoryManager | None = None,
    ) -> None:
        self._bus = internal_bus
        self._event_bus = event_bus
        self._pipeline = llm_pipeline
        self._context_window_mgr = context_window_mgr
        self._context_window = context_window
        self._model_config = model_config
        self._hippocampal = hippocampal
        self._monitor = monitor
        self._inhibition = inhibition
        self._session_roles_getter = session_roles_getter
        self._memory = memory
        self._messages: list[dict] = []
        self._msg_count_since_reflect = 0
        self._bus.subscribe("PlanDecided", self._on_plan)

    def _on_plan(self, event: PlanDecided) -> None:
        if self._monitor and event.plan.get("content", ""):
            self._monitor.record_user_input()
        self._apply_talkative_overrides(event.plan)
        logger.info(
            "ExecutionManager: executing plan session=%s abbreviated=%s",
            event.plan.get("session_id"),
            event.plan.get("abbreviated"),
        )
        self._execute_general(event.plan)

    @staticmethod
    def _apply_talkative_overrides(plan: dict) -> None:
        degree = plan.pop("talkative_degree", 0)
        if degree <= 0:
            return
        if degree >= 1:
            plan["abbreviated"] = True
        if degree >= 2:
            plan["max_tokens"] = min(plan.get("max_tokens", 0) or 120, 60)
        if degree >= 3:
            plan["run_reflexion"] = False
            plan["run_compression"] = False
        if degree >= 5:
            plan["streaming"] = False
            plan["show_thinking"] = False

    def _execute_general(self, plan: dict) -> None:
        session_id = plan.get("session_id", "")
        content = plan.get("content", "")
        abbreviated = plan.get("abbreviated", False)
        streaming = plan.get("streaming", not abbreviated)
        show_thinking = plan.get("show_thinking", not abbreviated)
        run_reflexion = plan.get("run_reflexion", not abbreviated)
        run_compression = plan.get("run_compression", not abbreviated)
        record_history = plan.get("record_history", True)
        if content:
            plan["tools_allowed"] = True

        if record_history and content:
            self._messages.append({"role": "user", "content": content})

        if content and self._memory:
            self._memory.short_term.add_turn("user", content)

        if show_thinking:
            self._event_bus.publish(
                MessageEvent(
                    timestamp=None,
                    source="execution",
                    session_id=session_id,
                    msg_type="chat",
                    content="",
                    state=StreamState.THINKING.value,
                    direction="stream",
                )
            )

        if self._session_roles_getter and not abbreviated:
            self._pipeline.set_session_roles_summary(self._session_roles_getter())

        on_token: Callable[[str], None] | None = None
        if streaming:

            def _on_token(delta: str) -> None:
                self._event_bus.publish(
                    MessageEvent(
                        timestamp=None,
                        source="execution",
                        session_id=session_id,
                        msg_type="chat",
                        content=delta,
                        state=StreamState.SPEAKING.value,
                        direction="stream",
                    )
                )

            on_token = _on_token

        try:
            response_text = self._pipeline.generate(
                plan=plan,
                messages=self._messages,
                on_token=on_token,
            )
        except Exception as e:
            response_text = f"[Error: {e}]"
            logger.exception("LLM call failed")

        if record_history:
            self._messages.append({"role": "assistant", "content": response_text})
            self._msg_count_since_reflect += 1

        if response_text and self._memory:
            self._memory.short_term.add_turn("assistant", response_text)

        logger.info(
            "ExecutionManager: response session=%s len=%d",
            session_id,
            len(response_text),
        )

        if show_thinking:
            self._event_bus.publish(
                MessageEvent(
                    timestamp=None,
                    source="execution",
                    session_id=session_id,
                    msg_type="chat",
                    content="",
                    state=StreamState.DONE.value,
                    direction="stream",
                )
            )

        self._event_bus.publish(
            MessageEvent(
                timestamp=None,
                source="execution",
                session_id=session_id,
                msg_type="chat",
                content=response_text,
                direction="response",
            )
        )

        if self._monitor:
            flags = self._monitor.record_output()
            self._handle_monitor_flags(flags)

        def _post_process() -> None:
            if run_reflexion and self._hippocampal:
                self._msg_count_since_reflect = self._hippocampal.maybe_run(
                    self._messages,
                    self._msg_count_since_reflect,
                )
            if run_compression and self._context_window_mgr:
                model_role = plan.get("model_role", "default")
                effective_ctx = (
                    self._model_config.get_effective_context_window(model_role)
                    if self._model_config
                    else self._context_window
                )
                model_name = self._model_config.get_model(model_role) if self._model_config else None
                self._context_window_mgr.check_and_summarize(self._messages, effective_ctx, model_name=model_name)

        if run_reflexion or run_compression:
            threading.Thread(target=_post_process, daemon=True).start()

    def _handle_monitor_flags(self, flags: list[str]) -> None:
        if "talkative" in flags and self._monitor and self._inhibition:
            degree = self._monitor.talkative_degree
            self._inhibition.apply_frequency_penalty(degree)
            logger.debug("Applied frequency penalty: degree=%d", degree)

    def compact_context(self) -> str:
        if self._context_window_mgr is None:
            return "Context manager not available"
        if len(self._messages) < 2:
            return "Not enough messages to compact"
        summary = self._context_window_mgr.compact(self._messages)
        keep = 6
        self._messages = [{"role": "system", "content": f"## Session Summary\n{summary}"}, *self._messages[-keep:]]
        return f"Compacted: {len(summary)} chars summary, kept last {keep} messages"
