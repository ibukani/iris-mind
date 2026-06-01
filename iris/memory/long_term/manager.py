"""長期記憶マネージャ (Episodic + Semantic + Vector)。

責務:
- エピソード記憶の CRUD
- 意味記憶の CRUD
- ベクトル検索 (VectorStore)
- 感情タグ付き記憶の検索 (emotion_search)
- 入力型強制 (coercion) と検索結果フォーマット (formatting) の委譲
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from iris.memory.long_term.coercion import coerce_episodic_input, coerce_semantic_input
from iris.memory.long_term.emotion_search import search_emotional_typed
from iris.memory.long_term.formatting import format_search_result
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
    from iris.memory.long_term.models import EmotionMemory


class LongTermMemoryManager(LongTermMemoryProtocol):
    """長期記憶 (Long-Term Memory)。
    エピソード記憶 (EpisodicStore) + 意味記憶 (SemanticStore) + ベクトル検索を統合管理する。

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
        payload = coerce_episodic_input(data, kind=kind)
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
        payload = coerce_semantic_input(data)
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
            return format_search_result(results)
        if self._vector_store is not None:
            results = self._vector_store.search(query=query, max_results=max_results, account_id=account_id)
            if room_id:
                results = [r for r in results if r.get("room_id") == room_id]
            return format_search_result(results)
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
        return format_search_result(results)

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
        if self._episodic is None:
            return []
        return search_emotional_typed(
            self._episodic,
            current_emotion=current_emotion,
            max_results=max_results,
            room_id=room_id,
        )

    @property
    def episodic(self) -> EpisodicStoreProtocol | None:
        return self._episodic

    @property
    def semantic(self) -> SemanticStoreProtocol | None:
        return self._semantic


__all__ = ["EpisodicInput", "LongTermMemoryManager", "LongTermMemoryProtocol", "SemanticInput"]
