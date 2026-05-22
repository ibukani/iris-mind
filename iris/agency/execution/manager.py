from __future__ import annotations

from collections.abc import Callable
import logging
from typing import TYPE_CHECKING, Any

from iris.agency.bus import InternalBus, PlanDecided
from iris.agency.execution.inhibition import InhibitionController
from iris.agency.execution.monitor import OutputMonitor
from iris.agency.execution.pipeline import LLMPipeline
from iris.agency.execution.post_processor import PostProcessor
from iris.event.event_bus import EventBus
from iris.event.event_types import InputReady, MessageEvent, MonitorFeedback
from iris.io.models import StreamState
from iris.llm.interrupt_token import InterruptToken

if TYPE_CHECKING:
    from iris.limbic.models import EmotionState
    from iris.memory.manager import MemoryManager

logger = logging.getLogger(__name__)


class ExecutionManager:
    TALKATIVE_ABBREVIATED_THRESHOLD = 1
    TALKATIVE_TOKEN_LIMIT_THRESHOLD = 2
    TALKATIVE_SKIP_POSTPROCESS_THRESHOLD = 3
    TALKATIVE_DISABLE_STREAM_THRESHOLD = 5

    def __init__(
        self,
        internal_bus: InternalBus,
        event_bus: EventBus,
        llm_pipeline: LLMPipeline,
        post_processor: PostProcessor,
        monitor: OutputMonitor | None = None,
        inhibition: InhibitionController | None = None,
        session_roles_getter: Callable[[], str] | None = None,
        memory: MemoryManager | None = None,
        messages: list[dict[str, Any]] | None = None,
    ) -> None:
        self._bus = internal_bus
        self._event_bus = event_bus
        self._pipeline = llm_pipeline
        self._monitor = monitor
        self._inhibition = inhibition
        self._session_roles_getter = session_roles_getter
        self._memory = memory
        self._post_processor = post_processor
        self._messages: list[dict[str, Any]] = messages if messages is not None else []
        self._interrupt_token: InterruptToken | None = None
        self._bus.subscribe("PlanDecided", self._on_plan)
        self._event_bus.subscribe("InputReady", self._on_input_ready)

    def get_state(self) -> dict:
        state = self._post_processor.get_state()
        state["msg_count"] = len(self._messages)
        state["talkative_degree"] = self._monitor.talkative_degree if self._monitor else 0
        return state

    def _on_input_ready(self, event: InputReady) -> None:
        # ユーザー入力が来た場合、現在実行中の処理があれば中断する
        context = event.context or {}
        if (
            not context.get("from_timer")
            and "system_event" not in context
            and self._interrupt_token
            and not self._interrupt_token.is_cancelled
        ):
            logger.info("ExecutionManager: cancelling current execution due to new user input")
            self._interrupt_token.cancel()

    def _on_plan(self, event: PlanDecided) -> None:
        plan = event.plan
        if self._monitor:
            if plan.get("content", ""):
                self._monitor.record_user_input()
            plan["talkative_degree"] = self._monitor.talkative_degree
            self._update_inhibition_state()
            self._apply_emotion_to_monitor(plan)

        self._apply_talkative_overrides(plan)

        if self._should_skip_proactive(plan):
            logger.info(
                "ExecutionManager: suppressed proactive (talkative=%d), skipping LLM",
                plan.get("talkative_degree", 0),
            )
            return

        logger.info(
            "ExecutionManager: executing plan session=%s abbreviated=%s",
            plan.get("session_id"),
            plan.get("abbreviated"),
        )
        self._execute_general(plan)

    def _update_inhibition_state(self) -> None:
        if self._monitor and self._inhibition:
            self._inhibition.set_output_frequency_state(
                self._monitor.outputs_since_last_input,
                self._monitor.frequency_exceeded,
            )

    def _apply_emotion_to_monitor(self, plan: dict[str, Any]) -> None:
        if not self._monitor:
            return
        emotion: EmotionState | None = plan.get("current_emotion")
        if emotion is None:
            return
        self._monitor.set_emotion_state(
            emotion.valence,
            emotion.arousal,
            emotion.dominance,
        )

    @classmethod
    def _apply_talkative_overrides(cls, plan: dict[str, Any]) -> None:
        degree: int = plan.get("talkative_degree", 0)
        if degree <= 0:
            return
        if degree >= cls.TALKATIVE_ABBREVIATED_THRESHOLD:
            plan["abbreviated"] = True
        if degree >= cls.TALKATIVE_TOKEN_LIMIT_THRESHOLD:
            current = plan.get("max_tokens", 0)
            if current > 0:
                plan["max_tokens"] = min(current, 256)
        if degree >= cls.TALKATIVE_SKIP_POSTPROCESS_THRESHOLD:
            plan["run_reflexion"] = False
            plan["run_compression"] = False
        if degree >= cls.TALKATIVE_DISABLE_STREAM_THRESHOLD:
            plan["streaming"] = False
            plan["show_thinking"] = False

    def _should_skip_proactive(self, plan: dict[str, Any]) -> bool:
        content: str = plan.get("content", "")
        if content:
            return False
        if not self._monitor:
            return False
        talkative: int = plan.get("talkative_degree", 0) or self._monitor.talkative_degree
        return talkative >= 2 or (self._monitor.frequency_exceeded and talkative >= 1)

    def _execute_general(self, plan: dict[str, Any]) -> None:
        content: str = plan.get("content", "")
        abbreviated: bool = plan.get("abbreviated", False)
        streaming: bool = plan.get("streaming", not abbreviated)
        show_thinking: bool = plan.get("show_thinking", not abbreviated)
        run_reflexion: bool = plan.get("run_reflexion", not abbreviated)
        run_compression: bool = plan.get("run_compression", not abbreviated)
        record_history: bool = plan.get("record_history", True)
        silent: bool = plan.get("silent", False)

        if silent:
            streaming = False
            show_thinking = False
            plan["allow_side_effects"] = False
            plan["max_tool_iterations"] = 3

            if not content:
                base_instruction = "システムからの内部指示: 現在の目標や欲求に基づき、Web検索や記憶検索を用いて知識を深めるための自律的な調査を行ってください。"
                if "proactive_reason" in plan:
                    base_instruction += f" (理由: {plan['proactive_reason']})"
                content = base_instruction
                plan["content"] = content

        if content:
            plan["tools_allowed"] = True

        self._prepare_execution_context(plan, content, show_thinking, record_history, silent)
        on_token = self._create_stream_callback() if streaming else None

        self._interrupt_token = InterruptToken()
        try:
            response_text = self._run_llm_generation(plan, on_token, self._interrupt_token)
            self._finalize_execution(plan, response_text, show_thinking, record_history, silent)
        finally:
            self._interrupt_token = None

        if not silent and (run_reflexion or run_compression):
            self._post_processor.trigger_post_processes(plan, run_reflexion, run_compression)

    def _prepare_execution_context(
        self, plan: dict[str, Any], content: str, show_thinking: bool, record_history: bool, silent: bool = False
    ) -> None:
        if record_history and content:
            role = "thought" if silent else "user"
            self._messages.append({"role": role, "content": content})
            self._post_processor.record_activity()

        if content and self._memory:
            role = "thought" if silent else "user"
            self._memory.short_term.add_turn(role, content)

        if show_thinking:
            self._event_bus.publish(
                MessageEvent(
                    timestamp=None,
                    source="execution",
                    msg_type="chat",
                    content="",
                    state=StreamState.THINKING.value,
                    direction="stream",
                )
            )

        if self._session_roles_getter and not plan.get("abbreviated", False):
            self._pipeline.set_session_roles_summary(self._session_roles_getter())

    def _create_stream_callback(self) -> Callable[[str], None]:
        def _on_token(delta: str) -> None:
            self._event_bus.publish(
                MessageEvent(
                    timestamp=None,
                    source="execution",
                    msg_type="chat",
                    content=delta,
                    state=StreamState.SPEAKING.value,
                    direction="stream",
                )
            )

        return _on_token

    def _run_llm_generation(
        self, plan: dict[str, Any], on_token: Callable[[str], None] | None, interrupt_token: InterruptToken | None
    ) -> str:
        try:
            if self._inhibition:
                self._inhibition.set_generating(True)
            response_text = self._pipeline.generate(
                plan=plan,
                messages=self._messages,
                on_token=on_token,
                interrupt_token=interrupt_token,
            )
        except Exception as e:
            response_text = f"[Error: {e}]"
            logger.exception("LLM call failed")
        finally:
            if self._inhibition:
                self._inhibition.set_generating(False)
        return response_text

    def _finalize_execution(
        self, plan: dict[str, Any], response_text: str, show_thinking: bool, record_history: bool, silent: bool = False
    ) -> None:
        session_id: str = plan.get("session_id", "")
        if not response_text:
            if show_thinking:
                self._event_bus.publish(
                    MessageEvent(
                        timestamp=None,
                        source="execution",
                        msg_type="chat",
                        content="",
                        state=StreamState.DONE.value,
                        direction="stream",
                    )
                )
            return

        if record_history:
            role = "thought" if silent else "assistant"
            self._messages.append({"role": role, "content": response_text})
            self._post_processor.record_activity()
            self._post_processor.increment_reflect_count()

        if response_text and self._memory:
            role = "thought" if silent else "assistant"
            self._memory.short_term.add_turn(role, response_text)

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
                    msg_type="chat",
                    content="",
                    state=StreamState.DONE.value,
                    direction="stream",
                )
            )

        if not silent:
            self._event_bus.publish(
                MessageEvent(
                    timestamp=None,
                    source="execution",
                    msg_type="chat",
                    content=response_text,
                    direction="response",
                )
            )

        if self._monitor:
            flags = self._monitor.record_output()
            self._handle_monitor_flags(flags)

    def _handle_monitor_flags(self, flags: list[str]) -> None:
        if not self._monitor:
            return

        if self._inhibition:
            self._inhibition.set_output_frequency_state(
                self._monitor.outputs_since_last_input,
                self._monitor.frequency_exceeded,
            )

        if "talkative" in flags and self._inhibition:
            degree = self._monitor.talkative_degree
            self._inhibition.apply_frequency_penalty(degree)
            logger.debug("Applied frequency penalty: degree=%d", degree)

        if flags:
            self._event_bus.publish(
                MonitorFeedback(
                    timestamp=None,
                    source="execution",
                    flags=flags,
                    content=",".join(flags),
                )
            )

    def flush_memory(self) -> None:
        self._post_processor.flush_memory()
        if self._memory:
            self._memory.flush()

    def compact_context(self) -> str:
        return self._post_processor.compact_context()
