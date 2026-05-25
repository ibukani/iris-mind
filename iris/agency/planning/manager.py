from __future__ import annotations

import time
from typing import TYPE_CHECKING

from iris.agency.bus import InternalBus, PlanDecided
from iris.agency.inhibition import InhibitionController
from iris.agency.planning.context_hint_builder import ContextHintBuilder
from iris.agency.planning.decisions import ProactiveJudge, ProactiveScoring
from iris.agency.planning.level_profile import resolve_level
from iris.agency.planning.models import Plan, PlanReason
from iris.agency.planning.question_generator import QuestionGenerator
from iris.agency.planning.strategies import ProactivePlanStrategy, ResponsePlanStrategy
from iris.event.event_bus import EventBus
from iris.event.event_types import InputReady
from iris.kernel.config import Config
from iris.memory.manager import MemoryManager

if TYPE_CHECKING:
    from iris.limbic.manager import LimbicManager
    from iris.limbic.models import EmotionState
    from iris.llm.bridge import LLMBridge
    from iris.memory.persona_profile import PersonaProfile

from loguru import logger


class PlanningManager:
    def __init__(
        self,
        internal_bus: InternalBus,
        event_bus: EventBus,
        inhibition: InhibitionController,
        scoring: ProactiveScoring,
        config: Config,
        memory: MemoryManager | None = None,
        limbic: LimbicManager | None = None,
        persona_profile: PersonaProfile | None = None,
        llm: LLMBridge | None = None,
    ) -> None:
        self._bus = internal_bus
        self._inhibition = inhibition
        self._limbic = limbic

        context_builder = ContextHintBuilder(memory=memory)
        question_gen = QuestionGenerator(llm=llm) if llm else None

        self._proactive_judge = ProactiveJudge(
            inhibition=inhibition,
            scoring=scoring,
            config=config.proactive,
            limbic=limbic,
            context_builder=context_builder,
        )
        self._proactive_strategy = ProactivePlanStrategy(
            persona_profile=persona_profile,
            question_gen=question_gen,
        )
        self._response_strategy = ResponsePlanStrategy(
            config=config.proactive,
            context_builder=context_builder,
        )
        event_bus.subscribe("InputReady", self._on_input_ready)

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
        limbic_mood = self._resolve_limbic_mood()
        limbic_drive = self._limbic.current_needs() if self._limbic else None
        gate = self._inhibition.evaluate(time.time())

        proactive_context = self._proactive_judge.decide(event, context, gate, limbic_mood, limbic_drive)
        if proactive_context is None:
            return
        plan = self._proactive_strategy.build_proactive(proactive_context, gate, limbic_mood)
        self._publish(plan, event.session_id, from_timer=True)

    def _on_user_input(self, event: InputReady) -> None:
        limbic_mood = self._resolve_limbic_mood()
        gate = self._inhibition.evaluate(time.time())
        self._inhibition.notify_user_activity()

        plan = self._response_strategy.build_response(event.content, gate, limbic_mood)
        self._publish(plan, event.session_id, from_timer=False)

    def _resolve_limbic_mood(self) -> EmotionState | None:
        if not self._limbic:
            return None
        emotion = self._limbic.current_emotion()
        self._inhibition.apply_limbic_modulation(emotion)
        return emotion

    def _publish(self, plan: Plan, session_id: str, from_timer: bool) -> None:
        resolved = resolve_level(plan.task_level, plan.overrides)
        resolved["content"] = plan.content
        resolved["context_hint"] = plan.context_hint
        resolved["streaming"] = not plan.silent
        resolved["silent"] = plan.silent
        if plan.silent:
            resolved["show_thinking"] = False
        resolved["record_history"] = True
        resolved["session_id"] = session_id
        resolved["situation"] = (
            "proactive"
            if plan.reason in (PlanReason.PROACTIVE_CURIOSITY, PlanReason.PROACTIVE_ESCALATION, PlanReason.TIMER_EVENT)
            else ""
        )

        logger.info(
            "PlanningManager: plan published session={} from_timer={} level={}",
            session_id,
            from_timer,
            plan.task_level,
        )
        self._bus.publish(PlanDecided(plan=resolved))
