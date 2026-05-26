from __future__ import annotations

from iris.agency.execution.executor import FlowExecutor
from iris.agency.planning.manager import PlanningManager


class AgencyManager:
    def __init__(
        self,
        planning: PlanningManager,
        execution: FlowExecutor,
    ) -> None:
        self.planning = planning
        self.execution = execution

    def get_state(self) -> dict:
        return {
            "planning": self.planning.get_state(),
            "execution": self.execution.get_state(),
        }

    def shutdown(self) -> None:
        self.execution.flush_memory()
        self.execution.shutdown()

    def compact_context(self) -> str:
        return "Compact not available"
