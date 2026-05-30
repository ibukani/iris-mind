from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from langchain_core.messages import HumanMessage

from iris.agency.execution.models import DynamicState, ExecutionState
from iris.agency.planning.models import Plan
from iris.agency.task_level import TASK_LEVELS
from iris.event.event_types import MessageEvent
from iris.io.models import StreamState
from iris.memory.models import text_block

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
        show_thinking = TASK_LEVELS[plan.task_level].show_thinking

        self._dynamic.current_plan = plan
        self._set_on_token_callback()

        if content:
            state["messages"].append(HumanMessage(content=content))
        if content and self._memory:
            is_system = content.startswith("[system]")
            self._memory.short_term.add_turn(
                "system" if is_system else "user",
                [text_block(content)],
                plan.user_id,
            )

        if show_thinking and self._event_bus:
            self._event_bus.publish(
                MessageEvent(
                    timestamp=None,
                    source="execution",
                    session_id=plan.session_id,
                    msg_type="chat",
                    content="",
                    state=StreamState.THINKING.value,
                    direction="stream",
                    room_id=plan.room_id,
                ),
            )

        if self._session_roles_getter:
            self._pipeline.set_session_roles_summary(self._session_roles_getter())
        if plan.user_id:
            self._pipeline.set_current_user_id(plan.user_id)

    def _set_on_token_callback(self) -> None:
        event_bus = self._event_bus
        if event_bus is None:
            return

        def _on_token(delta: str) -> None:
            plan = self._dynamic.current_plan
            event_bus.publish(
                MessageEvent(
                    timestamp=None,
                    source="execution",
                    session_id=plan.session_id if plan else "",
                    msg_type="chat",
                    content=delta,
                    state=StreamState.SPEAKING.value,
                    direction="stream",
                    room_id=plan.room_id if plan else "",
                ),
            )

        self._dynamic.on_token = _on_token
