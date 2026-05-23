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

    def __init__(self, modulation_strength: float = 0.5) -> None:
        self._modulation_strength = modulation_strength
        self._encounter_count: int = 0
        self._efficacy_history: list[float] = []

    def modulate(
        self,
        delta: EmotionDelta,
        current: EmotionState,
        big_five: dict[str, float] | None = None,
    ) -> EmotionDelta:
        """扁桃体からの感情変化量を調整する。

        制御則:
        - 現在の arousal が高い → delta を抑制（過剰反応防止）
        - 現在の valence が極端 → delta を減衰（感情の暴走防止）
        - modulation_strength が高いほど制御が強い
        - Neuroticism が高い → 制御を緩め、感情反応を許容
        - Agreeableness が高い → 負の感情をより抑制

        Args:
            delta: 扁桃体が出力した感情変化量
            current: 現在の感情状態
            big_five: Big Five スコア辞書 (key: trait name, value: 0-100)

        Returns:
            調整後の感情変化量
        """
        strength = self._modulation_strength

        if big_five is not None:
            neuroticism = big_five.get("neuroticism", 50) / 100.0
            strength *= 1.0 - (neuroticism - 0.5) * 0.4
            strength = max(0.1, min(1.0, strength))

        factor = 1.0

        if abs(current.valence) > 0.7:
            factor *= 1.0 - strength * 0.3

        if current.arousal > 0.6:
            factor *= 1.0 - strength * 0.4

        if big_five is not None:
            agreeableness = big_five.get("agreeableness", 50) / 100.0
            extraversion = big_five.get("extraversion", 50) / 100.0

            if delta.valence < 0 and agreeableness > 0.5:
                factor *= 1.0 - (agreeableness - 0.5) * 0.3
            if delta.valence > 0 and extraversion > 0.5:
                factor *= 1.0 + (extraversion - 0.5) * 0.2

        # メタ認知的再評価: 過去の調整効率から極端なdeltaを緩和
        delta_mag = math.sqrt(delta.valence**2 + delta.arousal**2 + delta.dominance**2)
        if self._efficacy_history and delta_mag > 0.3:
            avg_efficacy = sum(self._efficacy_history[-10:]) / max(len(self._efficacy_history[-10:]), 1)
            if avg_efficacy < 0.5:
                # 過去の経験から大部分が減衰されると学習 → 強いdeltaを余分に抑制
                extra_damp = min(0.3, (1.0 - avg_efficacy * 2) * 0.4)
                factor *= 1.0 - extra_damp

        # 慣れ: 延べ遭遇数に応じた制御強度の低下（刺激への適応）
        # ACC学習率の性格変調: Neuroticism高→慣れが遅い（負感情が減衰しにくい）
        habituation_rate = 0.015
        if big_five is not None:
            neuroticism = big_five.get("neuroticism", 50) / 100.0
            habituation_rate *= max(0.3, 1.0 - (neuroticism - 0.5) * 0.6)

        self._encounter_count += 1
        if self._encounter_count > 10:
            habituation = max(0.7, 1.0 - habituation_rate * min(self._encounter_count - 10, 20))
            factor *= habituation

        factor = max(0.3, factor)
        adjusted = delta.scale(factor)

        # 調整効率を履歴に記録（次回の再評価に使用）
        ratio = math.sqrt(adjusted.valence**2 + adjusted.arousal**2 + adjusted.dominance**2) / max(delta_mag, 0.01)
        self._efficacy_history.append(min(ratio, 1.0))
        if len(self._efficacy_history) > 50:
            self._efficacy_history.pop(0)

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
