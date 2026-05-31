from __future__ import annotations

from iris.agency.internal_bus import InternalBus
from iris.agency.planning.decisions import ProactiveJudge
from iris.agency.planning.strategies import ProactivePlanStrategy, ResponsePlanStrategy


class PlanningManager:
    def __init__(
        self,
        internal_bus: InternalBus,
        proactive_judge: ProactiveJudge,
        proactive_strategy: ProactivePlanStrategy,
        response_strategy: ResponsePlanStrategy,
    ) -> None:
        self._bus = internal_bus
        self._proactive_judge = proactive_judge
        self._proactive_strategy = proactive_strategy
        self._response_strategy = response_strategy

    def get_state(self) -> dict:
        return {
            "strategy_type": type(self._response_strategy).__name__,
            "proactive_judge_available": self._proactive_judge is not None,
        }
