from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from iris.limbic.models import EmotionState


class EmotionTemperatureModulator:
    VALENCE_LOW_THRESHOLD = -0.3
    VALENCE_HIGH_THRESHOLD = 0.5
    AROUSAL_HIGH_THRESHOLD = 0.6
    AROUSAL_LOW_THRESHOLD = 0.15
    DOMINANCE_LOW_THRESHOLD = 0.3
    DOMINANCE_HIGH_THRESHOLD = 0.6

    TEMP_ADJUST_NEGATIVE_VALENCE = 0.15
    TEMP_ADJUST_POSITIVE_VALENCE = -0.1
    TEMP_ADJUST_HIGH_AROUSAL = -0.15
    TEMP_ADJUST_LOW_AROUSAL = 0.2
    TEMP_ADJUST_LOW_DOMINANCE = 0.05
    TEMP_ADJUST_HIGH_DOMINANCE = -0.1

    DEFAULT_TEMPERATURE = 0.7

    @staticmethod
    def apply(plan: dict[str, Any], limbic_mood: EmotionState) -> None:
        temp: float = plan.get("temperature", EmotionTemperatureModulator.DEFAULT_TEMPERATURE)
        temp = EmotionTemperatureModulator._apply_valence_temp(plan, limbic_mood, temp)
        temp = EmotionTemperatureModulator._apply_arousal_temp(plan, limbic_mood, temp)
        temp = EmotionTemperatureModulator._apply_dominance_temp(plan, limbic_mood, temp)
        plan["temperature"] = max(0.2, min(1.0, temp))

    @staticmethod
    def _apply_valence_temp(plan: dict[str, Any], mood: EmotionState, temp: float) -> float:
        v = mood.valence
        if v < EmotionTemperatureModulator.VALENCE_LOW_THRESHOLD:
            current = plan.get("max_tokens", 0)
            if current > 0:
                plan["max_tokens"] = min(current, 256)
            if plan.get("abbreviated", False) is False:
                plan["tools_allowed"] = False
                plan["streaming"] = False
                return temp + EmotionTemperatureModulator.TEMP_ADJUST_NEGATIVE_VALENCE
        elif v > EmotionTemperatureModulator.VALENCE_HIGH_THRESHOLD:
            return max(temp + EmotionTemperatureModulator.TEMP_ADJUST_POSITIVE_VALENCE, 0.3)
        return temp

    @staticmethod
    def _apply_arousal_temp(plan: dict[str, Any], mood: EmotionState, temp: float) -> float:
        a = mood.arousal
        if a > EmotionTemperatureModulator.AROUSAL_HIGH_THRESHOLD:
            current = plan.get("max_tokens", 0)
            if current > 0:
                plan["max_tokens"] = min(current, 256)
            return max(temp + EmotionTemperatureModulator.TEMP_ADJUST_HIGH_AROUSAL, 0.3)
        if a < EmotionTemperatureModulator.AROUSAL_LOW_THRESHOLD:
            return min(temp + EmotionTemperatureModulator.TEMP_ADJUST_LOW_AROUSAL, 1.0)
        return temp

    @staticmethod
    def _apply_dominance_temp(plan: dict[str, Any], mood: EmotionState, temp: float) -> float:
        d = mood.dominance
        if d < EmotionTemperatureModulator.DOMINANCE_LOW_THRESHOLD:
            if plan.get("abbreviated", False) and plan["max_tokens"] == 80:
                plan["max_tokens"] = 50
            return temp + EmotionTemperatureModulator.TEMP_ADJUST_LOW_DOMINANCE
        if d > EmotionTemperatureModulator.DOMINANCE_HIGH_THRESHOLD:
            current = plan.get("max_tokens", 0)
            if current > 0:
                plan["max_tokens"] = min(current, 512)
            return max(temp + EmotionTemperatureModulator.TEMP_ADJUST_HIGH_DOMINANCE, 0.2)
        return temp
