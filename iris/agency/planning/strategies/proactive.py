from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from iris.agency.planning.emotion_temperature import EmotionTemperatureModulator

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
        self, context: dict[str, Any], gate: GateVerdict, limbic_mood: EmotionState | None = None
    ) -> dict[str, Any]:
        plan: dict[str, Any] = {
            "content": "",
            "situation": "proactive",
            "model_role": "default",
            "context_hint": context.get("context_hint", ""),
            "abbreviated": False,
            "tools_allowed": False,
            "streaming": False,
            "max_tokens": 512,
            "temperature": 0.8,
            "show_thinking": False,
            "run_reflexion": False,
            "run_compression": False,
            "record_history": True,
            "silent": False,
        }

        if context.get("is_silent_proactive", False):
            plan["silent"] = True
            plan["tools_allowed"] = True

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
                    plan["proactive_reason"] = question
                    plan["interest_topic"] = selected_topic
                else:
                    plan["proactive_reason"] = topic
            else:
                plan["proactive_reason"] = topic
        elif context.get("escalation"):
            plan["silent"] = False
            topic = context.get("topic", "")
            summary = context.get("summary", "")
            plan["content"] = (
                f"システムからの内部指示: あなたは自発的に『{topic}』に関する調査を行い、次のことが分かりました：『{summary}』。この知見を元に、ユーザーに対して『ねえ、さっき〜について考えていたんだけど……』というように、あなたの言葉で自然に自発的な話しかけを行ってください。"
            )
            plan["record_history"] = True
            plan["streaming"] = True

        if limbic_mood:
            EmotionTemperatureModulator.apply(plan, limbic_mood)
        plan["current_emotion"] = limbic_mood
        return plan
