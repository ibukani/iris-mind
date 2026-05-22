from __future__ import annotations

from collections.abc import Callable
import logging
from typing import TYPE_CHECKING, Any

from iris.agency.execution.modulation.coordinator import MonitorCoordinator
from iris.event.event_types import MessageEvent, ProactiveResultEvent
from iris.io.models import StreamState
from iris.llm.interrupt_token import InterruptToken

if TYPE_CHECKING:
    from iris.agency.execution.monitor import OutputMonitor
    from iris.agency.execution.pipeline import LLMPipeline
    from iris.agency.execution.post_processor import PostProcessor
    from iris.agency.inhibition import InhibitionController
    from iris.event.event_bus import EventBus
    from iris.memory.manager import MemoryManager

logger = logging.getLogger(__name__)


class ExecutionRunner:
    """実行の3フェーズ (prepare → generate → finalize) を管理。"""

    def __init__(
        self,
        event_bus: EventBus,
        messages: list[dict[str, Any]],
        pipeline: LLMPipeline,
        post_processor: PostProcessor,
        monitor: OutputMonitor | None = None,
        inhibition: InhibitionController | None = None,
        session_roles_getter: Callable[[], str] | None = None,
        memory: MemoryManager | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._messages = messages
        self._pipeline = pipeline
        self._post_processor = post_processor
        self._monitor = monitor
        self._inhibition = inhibition
        self._session_roles_getter = session_roles_getter
        self._memory = memory
        self._coordinator = MonitorCoordinator(event_bus, monitor, inhibition)
        self._interrupt_token: InterruptToken | None = None

    async def run(self, plan: dict[str, Any]) -> None:
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
            plan["priority"] = 1

            if not content:
                base_instruction = "システムからの内部指示: 現在の目標や欲求に基づき、Web検索や記憶検索を用いて知識を深めるための自律的な調査を行ってください。"
                if "proactive_reason" in plan:
                    base_instruction += f" (理由: {plan['proactive_reason']})"
                content = base_instruction
                plan["content"] = content

        if content:
            plan["tools_allowed"] = True

        self._prepare_context(plan, content, show_thinking, record_history, silent)
        on_token = self._create_stream_callback() if streaming else None

        self._interrupt_token = InterruptToken()
        try:
            response_text = await self._run_llm(plan, on_token, self._interrupt_token)
            self._finalize(plan, response_text, show_thinking, record_history, silent)
        finally:
            self._interrupt_token = None

        if not silent and (run_reflexion or run_compression):
            self._post_processor.trigger_post_processes(plan, run_reflexion, run_compression)

        if silent:
            success = bool(response_text and "[Error:" not in response_text)
            self._event_bus.publish(
                ProactiveResultEvent(
                    timestamp=None,
                    source="execution",
                    topic=plan.get("interest_topic", plan.get("proactive_reason", "")),
                    success=success,
                    content=response_text,
                )
            )

    def _prepare_context(
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

    async def _run_llm(
        self, plan: dict[str, Any], on_token: Callable[[str], None] | None, interrupt_token: InterruptToken | None
    ) -> str:
        try:
            if self._inhibition:
                self._inhibition.set_generating(True)
            response_text = await self._pipeline.generate(
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

    def _finalize(
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
            self._coordinator.handle_flags(flags)
