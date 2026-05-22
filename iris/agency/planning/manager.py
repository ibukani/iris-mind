from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from iris.agency.bus import InternalBus, PlanDecided
from iris.agency.execution.inhibition import GateVerdict, InhibitionController
from iris.agency.planning.context_hint_builder import ContextHintBuilder
from iris.agency.planning.decisions import ProactiveJudge, ProactiveScoring
from iris.agency.planning.question_generator import QuestionGenerator
from iris.agency.planning.strategies import ProactivePlanStrategy, ResponsePlanStrategy
from iris.event.event_bus import EventBus
from iris.event.event_types import InputReady
from iris.kernel.config import Config
from iris.memory.manager import MemoryManager

if TYPE_CHECKING:
    from iris.limbic.manager import LimbicManager
    from iris.limbic.models import DriveState, EmotionState
    from iris.llm.provider import LLMProvider
    from iris.memory.persona_profile import PersonaProfile

logger = logging.getLogger(__name__)


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
        llm: LLMProvider | None = None,
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

    def get_state(self) -> dict:
        gate = self._inhibition.evaluate(time.time())
        return {
            "suppressed": gate.suppressed,
            "reason": gate.reason,
            "go_signal": round(gate.go_signal, 2),
        }

    def _on_input_ready(self, event: InputReady) -> None:
        context = event.context or {}
        limbic_mood = self._resolve_limbic_mood()
        limbic_drive = self._limbic.current_drive() if self._limbic else None
        gate = self._inhibition.evaluate(time.time())

        if self._is_proactive_event(context):
            self._exec_proactive(event, context, gate, limbic_mood, limbic_drive)
            return

        self._inhibition.notify_user_activity()
        plan = self._response_strategy.build_response(event.content, gate, limbic_mood)
        plan["session_id"] = event.session_id
        logger.info(
            "PlanningManager: plan published session=%s from_timer=%s",
            event.session_id,
            False,
        )
        self._bus.publish(PlanDecided(plan=plan))

    def _resolve_limbic_mood(self) -> EmotionState | None:
        if not self._limbic:
            return None
        emotion = self._limbic.current_emotion()
        self._inhibition.apply_limbic_modulation(emotion)
        return emotion

    @staticmethod
    def _is_proactive_event(context: dict) -> bool:
        return bool(context.get("from_timer") or "system_event" in context or context.get("escalation"))

    def _exec_proactive(
        self,
        event: InputReady,
        context: dict,
        gate: GateVerdict,
        limbic_mood: EmotionState | None,
        limbic_drive: DriveState | None = None,
    ) -> None:
        proactive_context = self._proactive_judge.decide(event, context, gate, limbic_mood, limbic_drive)
        if proactive_context is None:
            return

        plan = self._proactive_strategy.build_proactive(proactive_context, gate, limbic_mood)
        plan["session_id"] = event.session_id
        logger.info(
            "PlanningManager: plan published session=%s from_timer=%s",
            event.session_id,
            True,
        )
        self._bus.publish(PlanDecided(plan=plan))
