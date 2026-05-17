from __future__ import annotations

import logging

from iris.event.event_bus import EventBus
from iris.event.event import InputReady
from iris.agency.bus import InternalBus
from iris.agency.planning.manager import PlanningManager
from iris.agency.execution.manager import ExecutionManager

logger = logging.getLogger(__name__)


class AgencyManager:
    def __init__(
        self,
        event_bus: EventBus,
        internal_bus: InternalBus,
        planning: PlanningManager,
        execution: ExecutionManager,
    ) -> None:
        self._event_bus = event_bus
        self._bus = internal_bus
        self._planning = planning
        self._execution = execution
        self._event_bus.subscribe("InputReady", self._on_input_ready)

    def _on_input_ready(self, event: InputReady) -> None:
        self._planning.handle(
            content=event.content,
            session_id=event.session_id,
            context=event.context,
        )
