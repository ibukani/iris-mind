from __future__ import annotations

import logging

from iris.agency.execution.inhibition import InhibitionController
from iris.agency.execution.manager import ExecutionManager
from iris.agency.planning.manager import PlanningManager

logger = logging.getLogger(__name__)


class AgencyManager:
    def __init__(
        self,
        planning: PlanningManager,
        execution: ExecutionManager,
        inhibition: InhibitionController | None = None,
    ) -> None:
        self._planning = planning
        self._execution = execution
        self._inhibition = inhibition

    def compact_context(self) -> str:
        return self._execution.compact_context()
