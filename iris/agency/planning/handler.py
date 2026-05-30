from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

from iris.agency.inhibition import InhibitionManager
from iris.agency.internal_bus import InternalBus, PlanDecided
from iris.agency.planning.decisions import ProactiveJudge
from iris.agency.planning.models import Plan
from iris.agency.planning.strategies import ProactivePlanStrategy, ResponsePlanStrategy
from iris.event.event_types import InputReady

if TYPE_CHECKING:
    from iris.event.event_bus import EventBus


class _PlanningEventHandler:
    def __init__(
        self,
        event_bus: EventBus,
        internal_bus: InternalBus,
        proactive_judge: ProactiveJudge,
        proactive_strategy: ProactivePlanStrategy,
        response_strategy: ResponsePlanStrategy,
        inhibition: InhibitionManager | None = None,
    ) -> None:
        self._bus = internal_bus
        self._proactive_judge = proactive_judge
        self._proactive_strategy = proactive_strategy
        self._response_strategy = response_strategy
        self._inhibition = inhibition

        event_bus.subscribe(InputReady, self._on_input_ready)

    def _on_input_ready(self, event: InputReady) -> None:
        context = event.context or {}
        if self._is_proactive_event(context):
            self._on_proactive_event(event, context)
        else:
            self._on_user_input(event)

    @staticmethod
    def _is_proactive_event(context: dict) -> bool:
        return bool(context.get("from_timer") or "system_event" in context or context.get("escalation"))

    def _on_proactive_event(self, event: InputReady, context: dict) -> None:
        if self._inhibition and self._inhibition.should_suppress_proactive():
            logger.debug("Proactive suppressed by inhibition")
            return
        proactive_context = self._proactive_judge.decide(event, context)
        if proactive_context is None:
            return
        plan = self._proactive_strategy.build_proactive(proactive_context)
        self._publish(
            plan, event.session_id, event.account_id or context.get("identity", ""), event.room_id, from_timer=True
        )

    def _on_user_input(self, event: InputReady) -> None:
        chaos_level = (event.context or {}).get("chaos_level", 0.0)
        plan = self._response_strategy.build_response(event.content, chaos_level=chaos_level, room_id=event.room_id)
        self._publish(plan, event.session_id, event.account_id, event.room_id, from_timer=False)

    def _publish(self, plan: Plan, session_id: str, account_id: str, room_id: str, from_timer: bool) -> None:
        plan.session_id = session_id
        plan.account_id = account_id
        plan.room_id = room_id
        if plan.silent:
            plan.overrides["allow_side_effects"] = False
            plan.overrides["max_tool_iterations"] = 3
            plan.overrides["priority"] = 1

        logger.info(
            "PlanningManager: plan published session={} from_timer={} level={}",
            plan.session_id,
            from_timer,
            plan.task_level,
        )
        self._bus.publish(PlanDecided(plan=plan))
