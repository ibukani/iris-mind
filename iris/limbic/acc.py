from __future__ import annotations

import logging

from iris.limbic.models import EmotionDelta, EmotionState

logger = logging.getLogger(__name__)


class AnteriorCingulateCortex:
    """前帯状皮質 (ACC): 感情制御・葛藤調整。

    脳科学:
      ACC は扁桃体からの感情シグナルと PFC からの合理的判断の間の
      葛藤を検出し、感情表出を適切に制御する。
      また、エラー検出・予測と実際の結果の不一致にも反応する。

    Phase 1: Big Five 未実装のため、基本的なゲイン制御のみ。
    Phase 2: Big Five の Neuroticism/Agreeableness による変調を追加。
    """

    def __init__(self, regulation_strength: float = 0.5) -> None:
        self._regulation_strength = regulation_strength

    def regulate(
        self,
        delta: EmotionDelta,
        current: EmotionState,
        big_five: dict | None = None,
    ) -> EmotionDelta:
        """扁桃体からの感情変化量を調整する。

        制御則:
        - 現在の arousal が高い → delta を抑制（過剰反応防止）
        - 現在の valence が極端 → delta を減衰（感情の暴走防止）
        - regulation_strength が高いほど制御が強い

        Args:
            delta: 扁桃体が出力した感情変化量
            current: 現在の感情状態
            big_five: Big Five スコア (Phase 2 以降)

        Returns:
            調整後の感情変化量
        """
        factor = 1.0

        if abs(current.valence) > 0.7:
            factor *= 1.0 - self._regulation_strength * 0.3

        if current.arousal > 0.6:
            factor *= 1.0 - self._regulation_strength * 0.4

        factor = max(0.1, factor)
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
