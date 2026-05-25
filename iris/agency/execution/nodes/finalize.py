from __future__ import annotations

from typing import TYPE_CHECKING, Any

from langchain_core.messages import AIMessage, ChatMessage

from iris.agency.execution.state import ExecutionState
from iris.event.event_types import MessageEvent, ProactiveResultEvent
from iris.io.models import StreamState

if TYPE_CHECKING:
    from iris.agency.execution.regulation.consolidator import Consolidator
    from iris.agency.execution.regulation.feedback import FeedbackCoordinator
    from iris.agency.execution.regulation.output_tracker import OutputTracker
    from iris.event.event_bus import EventBus
    from iris.memory.manager import MemoryManager

from loguru import logger


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

    async def __call__(self, state: ExecutionState) -> dict[str, Any] | None:
        plan = state["plan"]
        response_text = state.get("response_text", "")
        show_thinking = plan.get("show_thinking", False)
        silent = plan.get("silent", False)
        session_id = plan.get("session_id", "")

        if not response_text:
            self._publish_stream_done(show_thinking, session_id)
            state["completed"] = True
            return {"completed": True}

        self._record_history(state, response_text, silent)

        if response_text and self._memory:
            role = "thought" if silent else "assistant"
            self._memory.short_term.add_turn(role, response_text)

        logger.info("ExecutionGraph: response session={} len={}", session_id, len(response_text))

        self._publish_stream_done(show_thinking, session_id)

        if not silent:
            self._publish_response(session_id, response_text)

        self._process_feedback()

        if silent:
            self._publish_proactive_result(plan, response_text)

        state["completed"] = True
        return {"completed": True}

    def _publish_stream_done(self, show_thinking: bool, session_id: str) -> None:
        if not show_thinking or not self._event_bus:
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
            )
        )

    def _publish_response(self, session_id: str, response_text: str) -> None:
        if not self._event_bus:
            return
        self._event_bus.publish(
            MessageEvent(
                session_id=session_id,
                timestamp=None,
                source="execution",
                msg_type="chat",
                content=response_text,
                direction="response",
            )
        )

    def _record_history(self, state: ExecutionState, response_text: str, silent: bool) -> None:
        if silent:
            state["messages"].append(ChatMessage(role="thought", content=response_text))
        else:
            state["messages"].append(AIMessage(content=response_text))
        if self._consolidator:
            self._consolidator.record_activity()
            self._consolidator.increment_reflect_count()

    def _process_feedback(self) -> None:
        if not self._monitor:
            return
        flags = self._monitor.record_output()
        if self._coordinator:
            self._coordinator.process_feedback(flags)

    def _publish_proactive_result(self, plan: dict[str, Any], response_text: str) -> None:
        if not self._event_bus:
            return
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
