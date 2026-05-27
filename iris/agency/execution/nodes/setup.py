from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from langchain_core.messages import ChatMessage, HumanMessage

from iris.agency.execution.models import DynamicState, ExecutionState
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
        if silent and not content:
            curiosity_count = plan.modulation.curiosity_candidate_count
            if curiosity_count <= 1:
                base_instruction = "システムからの内部指示: 現在の目標や欲求に基づき、Web検索や記憶検索を用いて知識を深めるための自律的な調査を行ってください。"
            else:
                base_instruction = (
                    "システムからの内部指示: 以下の好奇心候補からランダムに1つ選び、調査・実行してください。\n"
                    + "\n".join(
                        f"{i + 1}. 現在の目標や欲求に関連する気になる話題を深掘りする" for i in range(curiosity_count)
                    )
                )
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
        if content and self._memory:
            role = "thought" if silent else "user"
            self._memory.short_term.add_turn(role, content, plan.user_identity)

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
        if plan.user_identity:
            self._pipeline.set_current_user_identity(plan.user_identity)

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
