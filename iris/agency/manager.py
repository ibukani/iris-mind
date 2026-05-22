from __future__ import annotations

import logging

from iris.agency.execution.manager import ExecutionManager
from iris.agency.inhibition import InhibitionController
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
        state: dict = {
            "execution": self._execution.get_state(),
        }
        if self._inhibition is not None:
            state["inhibition"] = self._inhibition.get_state()
        return state

    def compact_context(self) -> str:
        return self._execution.compact_context()

    def flush_memory(self) -> None:
        self._execution.flush_memory()
