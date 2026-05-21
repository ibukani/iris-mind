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

    def get_state(self) -> dict:
        return {
            "planning": self._planning.get_state(),
            "execution": self._execution.get_state(),
        }

    def compact_context(self) -> str:
        return self._execution.compact_context()

    def flush_memory(self) -> None:
        self._execution.flush_memory()
