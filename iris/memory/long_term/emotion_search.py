"""感情タグ付き記憶の検索ロジック。

episodic store 内の emotion_tag メタデータを持つエントリを、現在の感情 (PAD:
Pleasure-Arousal-Dominance) との類似度でランキングする。
"""

from __future__ import annotations

from collections.abc import Mapping
import math
from typing import Any

from iris.memory.long_term.models import EmotionMemory, EpisodicEntry
from iris.memory.long_term.store_protocols import EpisodicStoreProtocol


def pad_distance(a: Any, b: Mapping[str, Any]) -> float:
    """PAD 3次元 (valence / arousal / dominance) ユークリッド距離。"""
    a_val = a.valence
    a_aro = a.arousal
    a_dom = a.dominance
    b_val = float(b.get("valence", 0))
    b_aro = float(b.get("arousal", 0))
    b_dom = float(b.get("dominance", 0))
    return math.sqrt((a_val - b_val) ** 2 + (a_aro - b_aro) ** 2 + (a_dom - b_dom) ** 2)


def search_emotional_typed(
    episodic: EpisodicStoreProtocol,
    current_emotion: Any | None = None,
    max_results: int = 5,
    room_id: str = "",
) -> list[EmotionMemory]:
    """emotion_tag メタデータ付きエピソードを PAD 類似度でランキングする。

    current_emotion が None の場合は intensity の降順で返す。
    """
    if not episodic:
        return []
    all_entries = episodic.get_recent(episodic.max_entries)
    if room_id:
        all_entries = [e for e in all_entries if e.get("room_id") == room_id]
    emotion_entries = [e for e in all_entries if (e.get("metadata") or {}).get("type") == "emotion_tag"]
    if not emotion_entries:
        return []

    if current_emotion is None:
        ordered = sorted(
            emotion_entries,
            key=lambda e: (e.get("metadata") or {}).get("intensity", 0),
            reverse=True,
        )[:max_results]
        return [
            EmotionMemory(
                entry=EpisodicEntry.from_dict(e),
                intensity=(e.get("metadata") or {}).get("intensity", 0),
            )
            for e in ordered
        ]

    scored: list[tuple[float, dict]] = []
    for e in emotion_entries:
        meta = e.get("metadata") or {}
        meta_emotion = meta.get("emotion") or {}
        distance = pad_distance(current_emotion, meta_emotion)
        intensity = float(meta.get("intensity", 0))
        score = intensity / max(distance, 0.01)
        scored.append((score, e))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [
        EmotionMemory(
            entry=EpisodicEntry.from_dict(e),
            score=score,
            intensity=float((e.get("metadata") or {}).get("intensity", 0)),
        )
        for score, e in scored[:max_results]
    ]


__all__ = ["pad_distance", "search_emotional_typed"]
