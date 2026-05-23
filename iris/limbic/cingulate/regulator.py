from __future__ import annotations

import math

from loguru import logger

from iris.limbic.models import EmotionDelta, EmotionState


class AnteriorCingulateCortex:
    """前帯状皮質 (ACC): 感情制御・葛藤調整。

    脳科学:
      ACC は扁桃体からの感情シグナルと PFC からの合理的判断の間の
      葛藤を検出し、感情表出を適切に変調する。
      また、エラー検出・予測と実際の結果の不一致にも反応する。

    Big Five 相互作用:
      - Neuroticism 高 → 感情反応が増幅、制御が弱まる
      - Agreeableness 高 → 負の感情表出を抑制
      - Extraversion 高 → 正の感情を促進
    """

    def __init__(self, modulation_strength: float = 0.3) -> None:
        self._modulation_strength = modulation_strength
        self._encounter_count: int = 0
        self._efficacy_history: list[float] = []

    def modulate(
        self,
        delta: EmotionDelta,
        current: EmotionState,
        big_five: dict[str, float] | None = None,
    ) -> EmotionDelta:
        strength = self._apply_neuroticism_strength(self._modulation_strength, big_five)
        factor = 1.0
        factor *= self._state_damping_factor(current, strength)
        factor *= self._personality_factor(delta, big_five)
        factor *= self._meta_cognitive_factor(delta)
        factor *= self._compute_habituation(big_five)
        factor = max(0.3, factor)

        adjusted = delta.scale(factor)
        self._record_efficacy(delta, adjusted)

        logger.debug(
            "ACC modulate: delta=({:.3f}, {:.3f}, {:.3f}) current=({:.3f}, {:.3f}, {:.3f}) "
            "factor={:.3f} -> adjusted=({:.3f}, {:.3f}, {:.3f})",
            delta.valence,
            delta.arousal,
            delta.dominance,
            current.valence,
            current.arousal,
            current.dominance,
            factor,
            adjusted.valence,
            adjusted.arousal,
            adjusted.dominance,
        )
        return adjusted

    @staticmethod
    def _apply_neuroticism_strength(strength: float, big_five: dict[str, float] | None) -> float:
        if big_five is None:
            return strength
        neuroticism = big_five.get("neuroticism", 50) / 100.0
        strength *= 1.0 - (neuroticism - 0.5) * 0.4
        return max(0.1, min(1.0, strength))

    @staticmethod
    def _state_damping_factor(current: EmotionState, strength: float) -> float:
        f = 1.0
        if abs(current.valence) > 0.7:
            f *= 1.0 - strength * 0.3
        if current.arousal > 0.6:
            f *= 1.0 - strength * 0.4
        return f

    @staticmethod
    def _personality_factor(delta: EmotionDelta, big_five: dict[str, float] | None) -> float:
        if big_five is None:
            return 1.0
        agreeableness = big_five.get("agreeableness", 50) / 100.0
        extraversion = big_five.get("extraversion", 50) / 100.0
        f = 1.0
        if delta.valence < 0 and agreeableness > 0.5:
            f *= 1.0 - (agreeableness - 0.5) * 0.3
        if delta.valence > 0 and extraversion > 0.5:
            f *= 1.0 + (extraversion - 0.5) * 0.2
        return f

    def _meta_cognitive_factor(self, delta: EmotionDelta) -> float:
        if not self._efficacy_history:
            return 1.0
        delta_mag = math.sqrt(delta.valence**2 + delta.arousal**2 + delta.dominance**2)
        if delta_mag <= 0.3:
            return 1.0
        avg_efficacy = sum(self._efficacy_history[-10:]) / max(len(self._efficacy_history[-10:]), 1)
        if avg_efficacy >= 0.5:
            return 1.0
        extra_damp = min(0.3, (1.0 - avg_efficacy * 2) * 0.4)
        return 1.0 - extra_damp

    def _compute_habituation(self, big_five: dict[str, float] | None) -> float:
        rate = 0.005
        if big_five is not None:
            neuroticism = big_five.get("neuroticism", 50) / 100.0
            rate *= max(0.3, 1.0 - (neuroticism - 0.5) * 0.6)
        self._encounter_count += 1
        if self._encounter_count <= 10:
            return 1.0
        return max(0.7, 1.0 - rate * min(self._encounter_count - 10, 20))

    def _record_efficacy(self, delta: EmotionDelta, adjusted: EmotionDelta) -> None:
        delta_mag = math.sqrt(delta.valence**2 + delta.arousal**2 + delta.dominance**2)
        ratio = math.sqrt(adjusted.valence**2 + adjusted.arousal**2 + adjusted.dominance**2) / max(delta_mag, 0.01)
        self._efficacy_history.append(min(ratio, 1.0))
        if len(self._efficacy_history) > 50:
            self._efficacy_history.pop(0)
