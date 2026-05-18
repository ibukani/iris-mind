from __future__ import annotations

import logging
from typing import Any

from iris.limbic.models import EmotionState

logger = logging.getLogger(__name__)


class EmotionalMemory:
    """扁桃体-海馬相互作用: 記憶への感情タグ付け。

    脳科学:
      扁桃体と海馬は密接に連携し、感情を伴ったエピソード記憶の
      符号化と検索を強化する。感情強度の高い記憶ほど強く定着し、
      想起されやすくなる。

    Phase 1: 最小限のメモリタグ付けインターフェース。
    Phase 3: EpisodicStore / SemanticStore との本格統合。
    """

    def __init__(self) -> None:
        self._recent_tags: list[dict[str, Any]] = []

    def tag(self, content: str, emotion: EmotionState) -> None:
        """会話内容に感情タグを付与して記録する。

        Args:
            content: タグ付け対象のテキスト
            emotion: その時点の感情状態
        """
        tag = {
            "content": content[:100],
            "emotion": emotion.to_dict(),
            "intensity": abs(emotion.valence) * emotion.arousal,
        }
        self._recent_tags.append(tag)
        if len(self._recent_tags) > 50:
            self._recent_tags.pop(0)
        logger.debug("EmotionalMemory tagged: intensity=%.3f", tag["intensity"])

    def get_recent_tags(self, n: int = 5) -> list[dict[str, Any]]:
        """最近の感情タグを強度順で返す。"""
        sorted_tags = sorted(
            self._recent_tags,
            key=lambda t: t["intensity"],
            reverse=True,
        )
        return sorted_tags[:n]

    def salient_summary(self) -> str:
        """直近の感情的なトピックの要約を生成する。
        Phase 1 ではタグ件数のみ返す。
        """
        if not self._recent_tags:
            return ""
        n_positive = sum(1 for t in self._recent_tags if t["emotion"]["valence"] > 0.3)
        n_negative = sum(1 for t in self._recent_tags if t["emotion"]["valence"] < -0.3)
        parts = []
        if n_positive:
            parts.append(f"直近で{n_positive}件のポジティブな会話")
        if n_negative:
            parts.append(f"直近で{n_negative}件のネガティブな会話")
        return "、".join(parts) if parts else ""
