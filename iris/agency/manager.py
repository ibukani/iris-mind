from __future__ import annotations

import logging

from iris.event.event_bus import EventBus
from iris.event.event import InputReady
from iris.agency.bus import InternalBus
from iris.agency.planning.manager import PlanningManager
from iris.agency.planning.proactive_scorer import ProactiveScorer
from iris.agency.execution.manager import ExecutionManager

logger = logging.getLogger(__name__)


class AgencyManager:
    def __init__(
        self,
        event_bus: EventBus,
        internal_bus: InternalBus,
        planning: PlanningManager,
        execution: ExecutionManager,
        proactive_scorer: ProactiveScorer | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._bus = internal_bus
        self._planning = planning
        self._execution = execution
        self._proactive = proactive_scorer

        self._event_bus.subscribe("InputReady", self._on_input_ready)

        if self._proactive is not None:
            self._proactive.set_on_speak(self._on_proactive_trigger)

    def compact_context(self) -> str:
        return self._execution.compact_context()

    def _on_input_ready(self, event: InputReady) -> None:
        if self._proactive is not None:
            self._proactive.notify_user_activity()

        self._planning.handle(
            content=event.content,
            session_id=event.session_id,
            context=event.context,
        )

    def _on_proactive_trigger(self, scores: dict[str, float], total: float, trigger_type: str) -> None:
        self._planning.handle_proactive(scores, total, trigger_type)
