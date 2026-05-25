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
    def apply_execution_params(plan: dict[str, Any], limbic_mood: EmotionState) -> None:
        v = limbic_mood.valence
        a = limbic_mood.arousal
        d = limbic_mood.dominance

        if v < EmotionTemperatureModulator.VALENCE_LOW_THRESHOLD:
            current = plan.get("max_tokens", 0)
            if current > 0:
                plan["max_tokens"] = min(current, 256)

        if a > EmotionTemperatureModulator.AROUSAL_HIGH_THRESHOLD:
            current = plan.get("max_tokens", 0)
            if current > 0:
                plan["max_tokens"] = min(current, 256)

        if d > EmotionTemperatureModulator.DOMINANCE_HIGH_THRESHOLD:
            current = plan.get("max_tokens", 0)
            if current > 0:
                plan["max_tokens"] = min(current, 512)

    @staticmethod
    def compute_temperature(limbic_mood: EmotionState, base_temp: float = 0.7) -> float:
        v = limbic_mood.valence
        a = limbic_mood.arousal
        d = limbic_mood.dominance

        if v < EmotionTemperatureModulator.VALENCE_LOW_THRESHOLD:
            base_temp += EmotionTemperatureModulator.TEMP_ADJUST_NEGATIVE_VALENCE
        elif v > EmotionTemperatureModulator.VALENCE_HIGH_THRESHOLD:
            base_temp = max(base_temp + EmotionTemperatureModulator.TEMP_ADJUST_POSITIVE_VALENCE, 0.3)

        if a > EmotionTemperatureModulator.AROUSAL_HIGH_THRESHOLD:
            base_temp = max(base_temp + EmotionTemperatureModulator.TEMP_ADJUST_HIGH_AROUSAL, 0.3)
        if a < EmotionTemperatureModulator.AROUSAL_LOW_THRESHOLD:
            base_temp = min(base_temp + EmotionTemperatureModulator.TEMP_ADJUST_LOW_AROUSAL, 1.0)

        if d < EmotionTemperatureModulator.DOMINANCE_LOW_THRESHOLD:
            base_temp += EmotionTemperatureModulator.TEMP_ADJUST_LOW_DOMINANCE
        if d > EmotionTemperatureModulator.DOMINANCE_HIGH_THRESHOLD:
            base_temp = max(base_temp + EmotionTemperatureModulator.TEMP_ADJUST_HIGH_DOMINANCE, 0.2)

        return max(0.2, min(1.0, base_temp))
