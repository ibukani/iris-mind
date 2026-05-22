from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from iris.agency.execution.state import ExecutionState
from iris.event.event_types import MessageEvent, ProactiveResultEvent
from iris.io.models import StreamState

if TYPE_CHECKING:
    from iris.agency.execution.regulation.consolidator import Consolidator
    from iris.agency.execution.regulation.feedback import FeedbackCoordinator
    from iris.agency.execution.regulation.output_tracker import OutputTracker
    from iris.event.event_bus import EventBus
    from iris.memory.manager import MemoryManager

logger = logging.getLogger(__name__)


class FinalizeNode:
    def __init__(
        self,
        event_bus: EventBus | None = None,
        memory: MemoryManager | None = None,
        consolidator: Consolidator | None = None,
        monitor: OutputTracker | None = None,
        coordinator: FeedbackCoordinator | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._memory = memory
        self._consolidator = consolidator
        self._monitor = monitor
        self._coordinator = coordinator

    async def __call__(self, state: ExecutionState) -> None:
        plan = state["plan"]
        response_text = state.get("response_text", "")
        show_thinking = plan.get("show_thinking", False)
        record_history = plan.get("record_history", True)
        silent = plan.get("silent", False)
        session_id = plan.get("session_id", "")

        if not response_text:
            if show_thinking and self._event_bus:
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
            state["completed"] = True
            return

        if record_history:
            role = "thought" if silent else "assistant"
            state["messages"].append({"role": role, "content": response_text})
            if self._consolidator:
                self._consolidator.record_activity()
                self._consolidator.increment_reflect_count()

        if response_text and self._memory:
            role = "thought" if silent else "assistant"
            self._memory.short_term.add_turn(role, response_text)

        logger.info("ExecutionGraph: response session=%s len=%d", session_id, len(response_text))

        if show_thinking and self._event_bus:
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

        if not silent and self._event_bus:
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
            if self._coordinator:
                self._coordinator.process_feedback(flags)

        if silent and self._event_bus:
            success = bool(response_text and not response_text.startswith("[Error:"))
            self._event_bus.publish(
                ProactiveResultEvent(
                    timestamp=None,
                    source="execution",
                    topic=plan.get("interest_topic", plan.get("proactive_reason", "")),
                    success=success,
                    content=response_text,
                )
            )

        state["completed"] = True
