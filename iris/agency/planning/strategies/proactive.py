from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from iris.agency.planning.emotion_temperature import EmotionTemperatureModulator
from iris.agency.planning.models import Plan, PlanReason

if TYPE_CHECKING:
    from iris.agency.inhibition import GateVerdict
    from iris.agency.planning.question_generator import QuestionGenerator
    from iris.limbic.models import EmotionState
    from iris.memory.persona_profile import PersonaProfile


class ProactivePlanStrategy:
    def __init__(
        self,
        persona_profile: PersonaProfile | None = None,
        question_gen: QuestionGenerator | None = None,
    ) -> None:
        self._persona_profile = persona_profile
        self._question_gen = question_gen

    def build_proactive(
        self,
        context: dict[str, Any],
        gate: GateVerdict,
        limbic_mood: EmotionState | None = None,
    ) -> Plan:
        context_hint: str = context.get("context_hint", "")
        overrides: dict[str, Any] = {}

        if context.get("is_silent_proactive", False):
            topic = context.get("topic", "general")
            if self._persona_profile:
                interests = self._persona_profile.persona_data.get_interests()
                if interests:
                    import random

                    topics = [item["topic"] for item in interests]
                    weights = [item["weight"] for item in interests]
                    if sum(weights) <= 0:
                        weights = [1.0] * len(weights)
                    selected_topic = random.choices(topics, weights=weights, k=1)[0]
                    question = asyncio.run(self._question_gen.generate(selected_topic)) if self._question_gen else topic
                    overrides["proactive_reason"] = question
                    overrides["interest_topic"] = selected_topic
                else:
                    overrides["proactive_reason"] = topic
            else:
                overrides["proactive_reason"] = topic

            plan = Plan(
                content="",
                task_level="normal",
                silent=True,
                reason=PlanReason.PROACTIVE_CURIOSITY,
                context_hint=context_hint,
                overrides=overrides,
            )
        elif context.get("escalation"):
            topic = context.get("topic", "")
            summary = context.get("summary", "")
            content = f"システムからの内部指示: あなたは自発的に『{topic}』に関する調査を行い、次のことが分かりました：『{summary}』。この知見を元に、ユーザーに対して『ねえ、さっき〜について考えていたんだけど……』というように、あなたの言葉で自然に自発的な話しかけを行ってください。"
            plan = Plan(
                content=content,
                task_level="deep",
                silent=False,
                reason=PlanReason.PROACTIVE_ESCALATION,
                context_hint=context_hint,
                overrides=overrides,
            )
        else:
            plan = Plan(
                content="",
                task_level="light",
                silent=True,
                reason=PlanReason.TIMER_EVENT,
                context_hint=context_hint,
                overrides=overrides,
            )

        if limbic_mood:
            EmotionTemperatureModulator.apply_execution_params(overrides, limbic_mood)

        return plan
