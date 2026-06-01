from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

from iris.memory.long_term.models import (
    EpisodicInput,
    EpisodicScope,
    SearchHit,
    SemanticInput,
    SemanticScope,
)
from iris.memory.long_term.protocol import LongTermMemoryProtocol
from iris.memory.long_term.store_protocols import EpisodicStoreProtocol, SemanticStoreProtocol
from iris.memory.long_term.vector_store import VectorStore

if TYPE_CHECKING:
    from collections.abc import Mapping

    from iris.memory.long_term.models import EmotionMemory


def _format_search_result(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """検索結果を統一された辞書フォーマットに整形する。

    意味検索とベクトル検索で返却形式を同一にし、将来的な項目追加時の変更を一箇所に閉じるため。
    """
    return [
        {
            "content": r.get("content", ""),
            "tags": r.get("tags", []),
            "type": r.get("type", "unknown"),
            "score": round(r.get("score", 0.0), 4),
            "timestamp": r.get("timestamp", ""),
        }
        for r in results
    ]


def _coerce_episodic_input(data: Any, kind: str = "") -> EpisodicInput:
    if isinstance(data, EpisodicInput):
        return data
    if isinstance(data, str):
        return EpisodicInput(content=data, kind=kind)
    if isinstance(data, dict):
        return EpisodicInput(
            content=str(data.get("content") or data.get("summary") or ""),
            kind=str(data.get("kind", kind)),
            metadata=data.get("metadata"),
            room_id=str(data.get("room_id", "")),
            account_id=str(data.get("account_id", "")),
        )
    return EpisodicInput(content=str(data), kind=kind)


def _coerce_semantic_input(data: Any) -> SemanticInput:
    if isinstance(data, SemanticInput):
        return data
    if isinstance(data, dict):
        raw_tags = data.get("tags") or []
        tags: list[str] = [str(t) for t in raw_tags] if isinstance(raw_tags, list) else []
        return SemanticInput(
            content=str(data.get("content", "")),
            type=str(data.get("type", "lesson")),
            tags=tags,
            room_id=str(data.get("room_id", "")),
            account_id=str(data.get("account_id", "")),
        )
    return SemanticInput(content=str(data))


class LongTermMemoryManager(LongTermMemoryProtocol):
    """長期記憶 (Long-Term Memory)。
    エピソード記憶 (EpisodicStore) + 意味記憶 (SemanticStore) を統合管理する。

    エピソード記憶: 具体的な出来事・会話セッションの要約（JSONL）
    意味記憶: 知識・教訓・嗜好・性格特性（JSONL + ChromaDB ベクトル検索）

    脳科学対応: 海馬体 (hippocampal formation) と大脳皮質連合野。
    エピソード記憶は海馬、意味記憶は側頭葉・前頭葉が担う。
    """

    def __init__(
        self,
        episodic: EpisodicStoreProtocol | None = None,
        semantic: SemanticStoreProtocol | None = None,
        vector_store: VectorStore | None = None,
    ) -> None:
        self._episodic = episodic
        self._semantic = semantic
        self._vector_store = vector_store

    # ---- エピソード記憶 ----

    def store_episodic(self, data: Any, kind: str = "", room_id: str = "", account_id: str = "") -> None:
        if self._episodic is None:
            return
        payload = _coerce_episodic_input(data, kind=kind)
        if not payload.room_id and room_id:
            payload.room_id = room_id
        if not payload.account_id and account_id:
            payload.account_id = account_id
        summary = payload.content
        if payload.kind and not summary.startswith(f"[{payload.kind}]"):
            summary = f"[{payload.kind}] {summary}"
        if payload.metadata is not None:
            self._episodic.add(
                summary,
                metadata=payload.metadata,
                room_id=payload.room_id,
                account_id=payload.account_id,
            )
        else:
            self._episodic.add(
                summary,
                room_id=payload.room_id,
                account_id=payload.account_id,
            )

    def get_episodic_recent(self, n: int = 5, room_id: str = "", account_id: str = "") -> list[dict[str, Any]]:
        if self._episodic is None:
            return []
        return self._episodic.get_recent(n, room_id=room_id, account_id=account_id)

    def get_episodic_scope(self, scope: EpisodicScope) -> list[dict[str, Any]]:
        if self._episodic is None:
            return []
        return self._episodic.get_recent(self._episodic.max_entries, room_id=scope.room_id, account_id=scope.account_id)

    def clear_episodic(self) -> None:
        if self._episodic is not None:
            self._episodic.clear()

    # ---- 意味記憶 ----

    def store_semantic(self, data: Any, room_id: str = "", account_id: str = "") -> None:
        if self._semantic is None:
            return
        payload = _coerce_semantic_input(data)
        if not payload.room_id and room_id:
            payload.room_id = room_id
        if not payload.account_id and account_id:
            payload.account_id = account_id
        self._semantic.add(payload.to_dict(), room_id=payload.room_id, account_id=payload.account_id)

    def search_semantic(
        self,
        query: str,
        max_results: int = 3,
        room_id: str = "",
        account_id: str = "",
    ) -> list[dict[str, Any]]:
        if self._semantic is not None:
            results = self._semantic.search(query=query, max_results=max_results, account_id=account_id)
            if room_id:
                results = [r for r in results if r.get("room_id") == room_id]
            return _format_search_result(results)
        if self._vector_store is not None:
            results = self._vector_store.search(query=query, max_results=max_results, account_id=account_id)
            if room_id:
                results = [r for r in results if r.get("room_id") == room_id]
            return _format_search_result(results)
        return []

    def search_semantic_typed(
        self,
        query: str,
        max_results: int = 3,
        scope: SemanticScope | None = None,
    ) -> list[SearchHit]:
        scope = scope or SemanticScope()
        rows = self.search_semantic(
            query,
            max_results=max_results,
            room_id=scope.room_id,
            account_id=scope.account_id,
        )
        return [SearchHit.from_dict(r) for r in rows]

    def clear_semantic(self) -> None:
        if self._semantic is not None:
            self._semantic.clear()

    # ---- ベクトル検索 ----

    def search_vector(self, query: str, max_results: int = 3) -> list[dict[str, Any]]:
        if self._vector_store is None:
            return []
        results = self._vector_store.search(query=query, max_results=max_results)
        return _format_search_result(results)

    def search_vector_typed(self, query: str, max_results: int = 3) -> list[SearchHit]:
        return [SearchHit.from_dict(r) for r in self.search_vector(query, max_results=max_results)]

    # ---- 感情タグ検索 ----

    def search_emotional(
        self,
        current_emotion: Any | None = None,
        max_results: int = 5,
        room_id: str = "",
    ) -> list[dict[str, Any]]:
        results = self.search_emotional_typed(
            current_emotion=current_emotion,
            max_results=max_results,
            room_id=room_id,
        )
        return [r.to_dict() for r in results]

    def search_emotional_typed(
        self,
        current_emotion: Any | None = None,
        max_results: int = 5,
        room_id: str = "",
    ) -> list[EmotionMemory]:
        from iris.memory.long_term.models import EmotionMemory, EpisodicEntry

        if not self._episodic:
            return []
        all_entries = self._episodic.get_recent(self._episodic.max_entries)
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
                EmotionMemory(entry=EpisodicEntry.from_dict(e), intensity=(e.get("metadata") or {}).get("intensity", 0))
                for e in ordered
            ]

        scored: list[tuple[float, dict]] = []
        for e in emotion_entries:
            meta = e.get("metadata") or {}
            meta_emotion = meta.get("emotion") or {}
            distance = _pad_distance(current_emotion, meta_emotion)
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

    @property
    def episodic(self) -> EpisodicStoreProtocol | None:
        return self._episodic

    @property
    def semantic(self) -> SemanticStoreProtocol | None:
        return self._semantic


__all__ = ["EpisodicInput", "LongTermMemoryManager", "LongTermMemoryProtocol", "SemanticInput"]


def _pad_distance(a: Any, b: Mapping[str, Any]) -> float:
    a_val = a.valence
    a_aro = a.arousal
    a_dom = a.dominance
    b_val = float(b.get("valence", 0))
    b_aro = float(b.get("arousal", 0))
    b_dom = float(b.get("dominance", 0))
    return math.sqrt((a_val - b_val) ** 2 + (a_aro - b_aro) ** 2 + (a_dom - b_dom) ** 2)
