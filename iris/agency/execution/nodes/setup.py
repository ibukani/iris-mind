from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from langchain_core.messages import ChatMessage, HumanMessage

from iris.agency.execution.state import DynamicState, ExecutionState
from iris.agency.planning.models import Plan
from iris.agency.task_level import TASK_LEVELS
from iris.event.event_types import MessageEvent
from iris.io.models import StreamState

if TYPE_CHECKING:
    from iris.agency.execution.llm.gateway import LLMGateway
    from iris.agency.execution.regulation.consolidator import Consolidator
    from iris.event.event_bus import EventBus
    from iris.memory.manager import MemoryManager


class SetupNode:
    def __init__(
        self,
        pipeline: LLMGateway,
        event_bus: EventBus | None = None,
        memory: MemoryManager | None = None,
        consolidator: Consolidator | None = None,
        session_roles_getter: Callable[[], str] | None = None,
        dynamic: DynamicState | None = None,
    ) -> None:
        self._pipeline = pipeline
        self._event_bus = event_bus
        self._memory = memory
        self._consolidator = consolidator
        self._session_roles_getter = session_roles_getter
        self._dynamic = dynamic or DynamicState()

    async def __call__(self, state: ExecutionState) -> None:
        plan: Plan = state["plan"]
        content = plan.content
        silent = plan.silent
        show_thinking = TASK_LEVELS[plan.task_level].show_thinking
        if silent:
            show_thinking = False
        adj = state.get("talkative_adjustments")
        if adj and adj.show_thinking is not None:
            show_thinking = adj.show_thinking

        if silent and not content:
            base_instruction = "システムからの内部指示: 現在の目標や欲求に基づき、Web検索や記憶検索を用いて知識を深めるための自律的な調査を行ってください。"
            proactive_reason = plan.overrides.get("proactive_reason", "")
            if proactive_reason:
                base_instruction += f" (理由: {proactive_reason})"
            content = base_instruction
            plan.content = content

        self._set_on_token_callback()

        if content:
            if silent:
                state["messages"].append(ChatMessage(role="thought", content=content))
            else:
                state["messages"].append(HumanMessage(content=content))
            if self._consolidator:
                self._consolidator.record_activity()

        if content and self._memory:
            role = "thought" if silent else "user"
            self._memory.short_term.add_turn(role, content)

        if show_thinking and self._event_bus:
            self._event_bus.publish(
                MessageEvent(
                    timestamp=None,
                    source="execution",
                    msg_type="chat",
                    content="",
                    state=StreamState.THINKING.value,
                    direction="stream",
                ),
            )

        if self._session_roles_getter:
            self._pipeline.set_session_roles_summary(self._session_roles_getter())

    def _set_on_token_callback(self) -> None:
        event_bus = self._event_bus
        if event_bus is None:
            return

        def _on_token(delta: str) -> None:
            event_bus.publish(
                MessageEvent(
                    timestamp=None,
                    source="execution",
                    msg_type="chat",
                    content=delta,
                    state=StreamState.SPEAKING.value,
                    direction="stream",
                ),
            )

        self._dynamic.on_token = _on_token
