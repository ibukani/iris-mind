from __future__ import annotations

from loguru import logger

from iris.limbic.models import EmotionDelta, EmotionState


class AnteriorCingulateCortex:
    """前帯状皮質 (ACC): 感情制御・葛藤調整。

    脳科学:
      ACC は扁桃体からの感情シグナルと PFC からの合理的判断の間の
      葛藤を検出し、感情表出を適切に制御する。
      また、エラー検出・予測と実際の結果の不一致にも反応する。

    Big Five 相互作用:
      - Neuroticism 高 → 感情反応が増幅、制御が弱まる
      - Agreeableness 高 → 負の感情表出を抑制
      - Extraversion 高 → 正の感情を促進
    """

    def __init__(self, regulation_strength: float = 0.5) -> None:
        self._regulation_strength = regulation_strength

    def regulate(
        self,
        delta: EmotionDelta,
        current: EmotionState,
        big_five: dict[str, float] | None = None,
    ) -> EmotionDelta:
        """扁桃体からの感情変化量を調整する。

        制御則:
        - 現在の arousal が高い → delta を抑制（過剰反応防止）
        - 現在の valence が極端 → delta を減衰（感情の暴走防止）
        - regulation_strength が高いほど制御が強い
        - Neuroticism が高い → 制御を緩め、感情反応を許容
        - Agreeableness が高い → 負の感情をより抑制

        Args:
            delta: 扁桃体が出力した感情変化量
            current: 現在の感情状態
            big_five: Big Five スコア辞書 (key: trait name, value: 0-100)

        Returns:
            調整後の感情変化量
        """
        strength = self._regulation_strength

        if big_five is not None:
            neuroticism = big_five.get("neuroticism", 50) / 100.0
            agreeableness = big_five.get("agreeableness", 50) / 100.0
            extraversion = big_five.get("extraversion", 50) / 100.0

            strength *= 1.0 - (neuroticism - 0.5) * 0.4
            strength = max(0.1, min(1.0, strength))

        factor = 1.0

        if abs(current.valence) > 0.7:
            factor *= 1.0 - strength * 0.3

        if current.arousal > 0.6:
            factor *= 1.0 - strength * 0.4

        if big_five is not None:
            neuroticism = big_five.get("neuroticism", 50) / 100.0
            agreeableness = big_five.get("agreeableness", 50) / 100.0
            extraversion = big_five.get("extraversion", 50) / 100.0

            if delta.valence < 0 and agreeableness > 0.5:
                factor *= 1.0 - (agreeableness - 0.5) * 0.3
            if delta.valence > 0 and extraversion > 0.5:
                factor *= 1.0 + (extraversion - 0.5) * 0.2

        factor = max(0.3, factor)
        adjusted = delta.scale(factor)
        logger.debug(
            "ACC regulate: delta=(%.3f, %.3f, %.3f) current=(%.3f, %.3f, %.3f) "
            "factor=%.3f -> adjusted=(%.3f, %.3f, %.3f)",
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
