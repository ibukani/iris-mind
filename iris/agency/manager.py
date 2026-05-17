from __future__ import annotations

import logging

from iris.agency.bus import InternalBus
from iris.agency.execution.inhibition import InhibitionController
from iris.agency.execution.manager import ExecutionManager
from iris.agency.planning.manager import PlanningManager
from iris.agency.planning.timer_gate import TimerGate
from iris.event.event_bus import EventBus
from iris.event.event_types import InputReady

logger = logging.getLogger(__name__)


class AgencyManager:
    def __init__(
        self,
        event_bus: EventBus,
        internal_bus: InternalBus,
        planning: PlanningManager,
        execution: ExecutionManager,
        timer_gate: TimerGate | None = None,
        inhibition: InhibitionController | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._bus = internal_bus
        self._planning = planning
        self._execution = execution
        self._timer_gate = timer_gate
        self._inhibition = inhibition

        self._event_bus.subscribe("InputReady", self._on_input_ready)

        if self._timer_gate is not None:
            self._timer_gate.set_on_speak(self._on_proactive_trigger)

    def compact_context(self) -> str:
        return self._execution.compact_context()

    def _on_input_ready(self, event: InputReady) -> None:
        if self._inhibition is not None:
            self._inhibition.notify_user_activity()

        self._planning.handle(
            content=event.content,
            session_id=event.session_id,
            context=event.context,
        )

    def _on_proactive_trigger(self, scores: dict[str, float], total: float) -> None:
        self._planning.handle_proactive(scores, total)
