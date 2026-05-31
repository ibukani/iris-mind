from __future__ import annotations

from iris.agency.execution.executor import FlowExecutor
from iris.agency.inhibition import InhibitionManager
from iris.agency.planning.manager import PlanningManager


class AgencyManager:
    def __init__(
        self,
        planning: PlanningManager,
        execution: FlowExecutor,
        inhibition: InhibitionManager | None = None,
    ) -> None:
        self.planning = planning
        self.execution = execution
        self._inhibition = inhibition

    def get_state(self) -> dict:
        state: dict = {
            "planning": self.planning.get_state(),
            "execution": self.execution.get_state(),
        }
        if self._inhibition:
            state["inhibition"] = self._inhibition.get_state()
        return state

    def shutdown(self) -> None:
        self.execution.flush_memory()
        self.execution.shutdown()

    def compact_context(self) -> str:
        return "Compact not available"
