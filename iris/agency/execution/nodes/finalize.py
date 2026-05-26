from __future__ import annotations

from typing import TYPE_CHECKING, Any

from iris.agency.execution.state import ExecutionState
from iris.agency.planning.models import Plan
from iris.event.event_types import MessageEvent
from iris.io.models import StreamState

if TYPE_CHECKING:
    from iris.event.event_bus import EventBus

from loguru import logger


class FinalizeNode:
    def __init__(
        self,
        event_bus: EventBus | None = None,
    ) -> None:
        self._event_bus = event_bus

    async def __call__(self, state: ExecutionState) -> dict[str, Any] | None:
        plan: Plan = state["plan"]
        response_text = state.get("response_text", "")
        session_id = plan.session_id

        if not response_text:
            self._publish_done(session_id)
            state["completed"] = True
            return {"completed": True}

        logger.info("ExecutionGraph: response session={} len={}", session_id, len(response_text))

        self._publish_done(session_id)
        state["completed"] = True
        return {"completed": True}

    def _publish_done(self, session_id: str) -> None:
        if not self._event_bus:
            return
        self._event_bus.publish(
            MessageEvent(
                session_id=session_id,
                timestamp=None,
                source="execution",
                msg_type="chat",
                content="",
                state=StreamState.DONE.value,
                direction="stream",
            ),
        )
