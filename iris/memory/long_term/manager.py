from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from collections.abc import Mapping


from iris.memory.long_term.protocols import EpisodicStoreProtocol, SemanticStoreProtocol
from iris.memory.long_term.vector_store import VectorStore


def _format_search_result(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """検索結果を統一された辞書フォーマットに整形する。

    なぜこの設計にしたか:
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


class LongTermMemoryProtocol(Protocol):
    """長期記憶のインターフェース。

    なぜこの設計にしたか:
    他のレイヤーが具象クラスである LongTermMemoryManager に直接依存するのを防ぎ、
    モック化やテスト用の代替実装を容易にするため。
    """

    @property
    def episodic(self) -> EpisodicStoreProtocol | None: ...

    @property
    def semantic(self) -> SemanticStoreProtocol | None: ...

    def store_episodic(self, data: Any, kind: str = "") -> None: ...
    def get_episodic_recent(self, n: int = 5) -> list[dict[str, Any]]: ...
    def clear_episodic(self) -> None: ...
    def store_semantic(self, data: Any) -> None: ...
    def search_semantic(self, query: str, max_results: int = 3) -> list[dict[str, Any]]: ...
    def clear_semantic(self) -> None: ...
    def search_vector(self, query: str, max_results: int = 3) -> list[dict[str, Any]]: ...
    def search_emotional(
        self,
        current_emotion: Any | None = None,
        max_results: int = 5,
    ) -> list[dict[str, Any]]: ...


class LongTermMemoryManager:
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
    ):
        self._episodic = episodic
        self._semantic = semantic
        self._vector_store = vector_store

    # ---- エピソード記憶 ----

    def store_episodic(self, data: Any, kind: str = "") -> None:
        if self._episodic is None:
            return
        summary = ""
        if isinstance(data, str):
            summary = data
        elif isinstance(data, dict):
            summary = data.get("content") or data.get("summary") or str(data)
            kind = data.get("kind", kind)
        if kind and not summary.startswith(f"[{kind}]"):
            summary = f"[{kind}] {summary}"
        self._episodic.add(summary)

    def get_episodic_recent(self, n: int = 5) -> list[dict[str, Any]]:
        if self._episodic is None:
            return []
        return self._episodic.get_recent(n)

    def clear_episodic(self) -> None:
        if self._episodic is not None:
            self._episodic.clear()

    # ---- 意味記憶 ----

    def store_semantic(self, data: Any) -> None:
        if self._semantic is None:
            return
        if isinstance(data, dict):
            self._semantic.add(data)
        else:
            self._semantic.add({"content": str(data)})

    def search_semantic(self, query: str, max_results: int = 3) -> list[dict[str, Any]]:
        if self._semantic is not None:
            results = self._semantic.search(query=query, max_results=max_results)
            return _format_search_result(results)
        if self._vector_store is not None:
            results = self._vector_store.search(query=query, max_results=max_results)
            return _format_search_result(results)
        return []

    def clear_semantic(self) -> None:
        if self._semantic is not None:
            self._semantic.clear()

    # ---- ベクトル検索 ----

    def search_vector(self, query: str, max_results: int = 3) -> list[dict[str, Any]]:
        if self._vector_store is None:
            return []
        results = self._vector_store.search(query=query, max_results=max_results)
        return _format_search_result(results)

    # ---- 感情タグ検索 ----

    def search_emotional(
        self,
        current_emotion: Any | None = None,
        max_results: int = 5,
    ) -> list[dict[str, Any]]:
        if not self._episodic:
            return []
        all_entries = self._episodic.get_recent(self._episodic.max_entries)
        emotion_entries = [e for e in all_entries if e.get("metadata", {}).get("type") == "emotion_tag"]
        if not emotion_entries:
            return []

        if current_emotion is None:
            return sorted(
                emotion_entries,
                key=lambda e: e.get("metadata", {}).get("intensity", 0),
                reverse=True,
            )[:max_results]

        scored: list[tuple[float, dict]] = []
        for e in emotion_entries:
            meta = e.get("metadata", {})
            meta_emotion = meta.get("emotion", {})
            distance = _pad_distance(current_emotion, meta_emotion)
            intensity = meta.get("intensity", 0)
            score = intensity / max(distance, 0.01)
            scored.append((score, e))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [e for _, e in scored[:max_results]]

    @property
    def episodic(self) -> EpisodicStoreProtocol | None:
        return self._episodic

    @property
    def semantic(self) -> SemanticStoreProtocol | None:
        return self._semantic


def _pad_distance(
    a: Any,
    b: Mapping[str, Any],
) -> float:
    a_val = a.valence
    a_aro = a.arousal
    a_dom = a.dominance
    b_val = float(b.get("valence", 0))
    b_aro = float(b.get("arousal", 0))
    b_dom = float(b.get("dominance", 0))
    return math.sqrt((a_val - b_val) ** 2 + (a_aro - b_aro) ** 2 + (a_dom - b_dom) ** 2)
