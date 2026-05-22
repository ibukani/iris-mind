from __future__ import annotations

from iris.agency.execution.executor import FlowExecutor
from iris.agency.inhibition import InhibitionController
from iris.agency.planning.manager import PlanningManager


class AgencyManager:
    def __init__(
        self,
        planning: PlanningManager,
        execution: FlowExecutor,
        inhibition: InhibitionController,
    ) -> None:
        self.planning = planning
        self.execution = execution
        self.inhibition = inhibition

    def get_state(self) -> dict:
        return {
            "execution": self.execution.get_state(),
            "inhibition": self.inhibition.get_state(),
        }
