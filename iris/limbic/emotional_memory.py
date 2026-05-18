from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
import logging
import math
from typing import Any

from iris.limbic.models import EmotionState
from iris.memory.stores import EpisodicStore, SemanticStore

logger = logging.getLogger(__name__)

_EMOTION_INTENSITY_THRESHOLD = 0.15


class EmotionalMemory:
    """扁桃体-海馬相互作用: 記憶への感情タグ付け。

    脳科学:
      扁桃体と海馬は密接に連携し、感情を伴ったエピソード記憶の
      符号化と検索を強化する。感情強度の高い記憶ほど強く定着し、
      想起されやすくなる。
    """

    def __init__(
        self,
        episodic_store: EpisodicStore | None = None,
        semantic_store: SemanticStore | None = None,
    ) -> None:
        self._episodic_store = episodic_store
        self._semantic_store = semantic_store
        self._recent_tags: list[dict[str, Any]] = []

    def tag(self, content: str, emotion: EmotionState) -> None:
        """会話内容に感情タグを付与して記録する。

        感情強度が閾値を超えた場合、EpisodicStore / SemanticStore にも永続化する。

        Args:
            content: タグ付け対象のテキスト
            emotion: その時点の感情状態
        """
        emotion_dict = emotion.to_dict()
        intensity = abs(emotion.valence) * emotion.arousal
        tag = {
            "content": content[:100],
            "emotion": emotion_dict,
            "intensity": round(intensity, 4),
        }
        self._recent_tags.append(tag)
        if len(self._recent_tags) > 50:
            self._recent_tags.pop(0)

        if intensity > _EMOTION_INTENSITY_THRESHOLD and self._episodic_store:
            summary = content[:80]
            self._episodic_store.add(
                summary=summary,
                metadata={
                    "type": "emotion_tag",
                    "emotion": emotion_dict,
                    "intensity": round(intensity, 4),
                },
            )

        if intensity > _EMOTION_INTENSITY_THRESHOLD and self._semantic_store:
            self._semantic_store.add(
                {
                    "content": content[:120],
                    "type": "emotional_memory",
                    "tags": ["emotion", _emotion_label(emotion)],
                    "emotion": emotion_dict,
                    "intensity": round(intensity, 4),
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            )

        logger.debug("EmotionalMemory tagged: intensity=%.3f label=%s", intensity, _emotion_label(emotion))

    def get_recent_tags(self, n: int = 5) -> list[dict[str, Any]]:
        """最近の感情タグを強度順で返す。"""
        sorted_tags = sorted(
            self._recent_tags,
            key=lambda t: t["intensity"],
            reverse=True,
        )
        return sorted_tags[:n]

    def salient_summary(self) -> str:
        """直近の感情的なトピックの要約を生成する。"""
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

    def search_by_emotion(
        self,
        target: EmotionState,
        max_results: int = 5,
    ) -> list[dict[str, Any]]:
        """感情状態に近い記憶を検索（強度順）。

        EpisodicStore の永続化された感情タグから、
        指定された感情状態とのPAD距離が近いものを返す。

        Args:
            target: 検索基準となる感情状態
            max_results: 最大件数

        Returns:
            感情距離が近い順の記憶リスト
        """
        if not self._episodic_store:
            return []

        all_entries = self._episodic_store.get_recent(self._episodic_store.max_entries)
        scored: list[tuple[float, dict[str, Any]]] = []

        for entry in all_entries:
            meta = entry.get("metadata")
            if not meta or meta.get("type") != "emotion_tag":
                continue
            meta_emotion = meta.get("emotion")
            if not meta_emotion:
                continue
            distance = _pad_distance(target, meta_emotion)
            intensity = meta.get("intensity", 0)
            score = intensity / max(distance, 0.01)
            scored.append((score, entry))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [e for _, e in scored[:max_results]]


def _pad_distance(a: EmotionState | Mapping[str, Any], b: Mapping[str, Any] | EmotionState) -> float:
    a_val = float(a.valence) if isinstance(a, EmotionState) else float(a.get("valence", 0))
    a_aro = float(a.arousal) if isinstance(a, EmotionState) else float(a.get("arousal", 0))
    a_dom = float(a.dominance) if isinstance(a, EmotionState) else float(a.get("dominance", 0))
    b_val = float(b.valence) if isinstance(b, EmotionState) else float(b.get("valence", 0))
    b_aro = float(b.arousal) if isinstance(b, EmotionState) else float(b.get("arousal", 0))
    b_dom = float(b.dominance) if isinstance(b, EmotionState) else float(b.get("dominance", 0))
    return math.sqrt((a_val - b_val) ** 2 + (a_aro - b_aro) ** 2 + (a_dom - b_dom) ** 2)


def _emotion_label(emotion: EmotionState) -> str:
    v, a, d = emotion.valence, emotion.arousal, emotion.dominance
    if v > 0.5 and a > 0.4:
        return "joy"
    if v < -0.5 and a > 0.4:
        return "anger"
    if v < -0.3 and a < 0.3:
        return "sadness"
    if a > 0.6 and d < 0.3:
        return "anxiety"
    if v > 0.3 and a < 0.3:
        return "calm"
    if v > 0.4 and d > 0.5:
        return "confidence"
    return "neutral"
