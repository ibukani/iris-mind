from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
import math
from typing import Any, TypedDict

from loguru import logger

from iris.limbic.models import EmotionState
from iris.memory.long_term.stores import EpisodicStore, SemanticStore

_EMOTION_INTENSITY_THRESHOLD = 0.15


class EmotionTag(TypedDict):
    content: str
    emotion: dict[str, float]
    intensity: float


def _pad_to_tuple(v: EmotionState | Mapping[str, Any]) -> tuple[float, float, float]:
    if isinstance(v, EmotionState):
        return (v.valence, v.arousal, v.dominance)
    return (float(v.get("valence", 0)), float(v.get("arousal", 0)), float(v.get("dominance", 0)))


def _pad_distance(a: EmotionState | Mapping[str, Any], b: Mapping[str, Any] | EmotionState) -> float:
    """PADユークリッド距離（感情強度の差を測る）"""
    a_v, a_a, a_d = _pad_to_tuple(a)
    b_v, b_a, b_d = _pad_to_tuple(b)
    return math.sqrt((a_v - b_v) ** 2 + (a_a - b_a) ** 2 + (a_d - b_d) ** 2)


def _pad_cosine(a: EmotionState | Mapping[str, Any], b: Mapping[str, Any] | EmotionState) -> float:
    """PADコサイン類似度（感情タイプの方向一致度）"""
    a_v, a_a, a_d = _pad_to_tuple(a)
    b_v, b_a, b_d = _pad_to_tuple(b)
    dot = a_v * b_v + a_a * b_a + a_d * b_d
    na = math.sqrt(a_v * a_v + a_a * a_a + a_d * a_d)
    nb = math.sqrt(b_v * b_v + b_a * b_a + b_d * b_d)
    if na * nb == 0:
        return 0.0
    return dot / (na * nb)


def _pad_distance_combined(a: EmotionState | Mapping[str, Any], b: Mapping[str, Any] | EmotionState) -> float:
    """ユークリッド + コサイン ハイブリッド距離。

    コサイン距離 (1 - cos) で方向不一致をペナルティとしてユークリッド距離に乗算。
    同じ方向ならユークリッド距離そのまま、逆方向なら数倍に増幅。
    """
    euclidean = _pad_distance(a, b)
    cosine_sim = _pad_cosine(a, b)
    return euclidean * (2.0 - cosine_sim)


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
        self._recent_tags: list[EmotionTag] = []

    def _push_recent_tag(self, tag: EmotionTag) -> None:
        self._recent_tags.append(tag)
        if len(self._recent_tags) > 50:
            self._recent_tags.pop(0)

    def _persist_episodic(self, content: str, emotion_dict: dict[str, float], intensity: float) -> None:
        if self._episodic_store is None:
            return
        self._episodic_store.add(
            summary=content[:80],
            metadata={
                "type": "emotion_tag",
                "emotion": emotion_dict,
                "intensity": round(intensity, 4),
            },
        )

    def _persist_semantic(self, content: str, emotion_dict: dict[str, float], label: str, intensity: float) -> None:
        if self._semantic_store is None:
            return
        self._semantic_store.add(
            {
                "content": content[:120],
                "type": "emotional_memory",
                "tags": ["emotion", label],
                "emotion": emotion_dict,
                "intensity": round(intensity, 4),
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )

    def encode(self, content: str, emotion: EmotionState) -> None:
        emotion_dict = emotion.to_dict()
        intensity = abs(emotion.valence) * emotion.arousal
        tag: EmotionTag = {
            "content": content[:100],
            "emotion": emotion_dict,
            "intensity": round(intensity, 4),
        }
        self._push_recent_tag(tag)

        if intensity > _EMOTION_INTENSITY_THRESHOLD:
            self._persist_episodic(content, emotion_dict, intensity)
            self._persist_semantic(content, emotion_dict, _emotion_label(emotion), intensity)

        logger.debug("Hippocampus encoded: intensity=%.3f label=%s", intensity, _emotion_label(emotion))

    def get_recent_tags(self, n: int = 5) -> list[EmotionTag]:
        sorted_tags = sorted(
            self._recent_tags,
            key=lambda t: t["intensity"],
            reverse=True,
        )
        return sorted_tags[:n]

    def summarize_salience(self) -> str:
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

    def retrieve_by_affect(
        self,
        target: EmotionState,
        max_results: int = 5,
    ) -> list[dict[str, Any]]:
        if not self._episodic_store:
            return []

        all_entries = self._episodic_store.get_recent(self._episodic_store.max_entries)
        scored: list[tuple[float, dict[str, Any]]] = []
        target_sign = 1 if target.valence >= 0 else -1

        for entry in all_entries:
            meta = entry.get("metadata")
            if not meta or meta.get("type") != "emotion_tag":
                continue
            meta_emotion = meta.get("emotion")
            if not meta_emotion:
                continue
            distance = _pad_distance_combined(target, meta_emotion)
            intensity = meta.get("intensity", 0)
            score = intensity / max(distance, 0.01)

            # 気分一致効果: 現在の感情と記憶のvalence方向が一致→促進
            meta_valence = float(meta_emotion.get("valence", 0))
            if (meta_valence >= 0) == (target_sign >= 0):
                score *= 1.2

            scored.append((score, entry))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [e for _, e in scored[:max_results]]


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
