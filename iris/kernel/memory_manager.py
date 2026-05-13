"""
MemoryManager — 記憶操作の一元管理

EpisodicStore, SemanticStore, VectorStore を統合し、
ProactiveEngine や AgentKernel から利用する高水準APIを提供する。
"""
from __future__ import annotations

import logging
from typing import Any

from iris.memory.stores import EpisodicStore, SemanticStore
from iris.memory.vector_store import VectorStore

logger = logging.getLogger(__name__)


class MemoryManager:
    """記憶の読み書きを一元管理するマネージャー。"""

    def __init__(
        self,
        episodic: EpisodicStore,
        semantic: SemanticStore,
        vector_store: VectorStore | None = None,
    ) -> None:
        self._episodic = episodic
        self._semantic = semantic
        self._vector_store = vector_store

    # ── 検索 ──────────────────────────────────────────────

    def search_semantic(self, query: str, max_results: int = 3) -> list[dict[str, Any]]:
        """意味記憶から関連エントリを検索する。

        Returns:
            スコア付きエントリのリスト。スコアは 0.0〜1.0。
        """
        results: list[dict[str, Any]] = []

        # SemanticStoreのハイブリッド検索（ChromaDB + BM25）
        try:
            vector_results = self._semantic.search(
                query=query, max_results=max_results
            )
            for vr in vector_results:
                results.append({
                    "content": vr.get("content", ""),
                    "tags": vr.get("tags", []),
                    "type": vr.get("type", "unknown"),
                    "score": round(vr.get("score", 0.0), 4),
                    "timestamp": vr.get("timestamp", ""),
                })
        except Exception as e:
            logger.warning("SemanticStore.search failed: %s", e)

        # VectorStore直アクセス（後方互換用）
        if self._vector_store is not None and not results:
            try:
                vector_results = self._vector_store.search(
                    query=query, max_results=max_results
                )
                for vr in vector_results:
                    results.append({
                        "content": vr.get("content", ""),
                        "tags": vr.get("tags", []),
                        "type": vr.get("type", "unknown"),
                        "score": round(vr.get("score", 0.0), 4),
                        "timestamp": vr.get("timestamp", ""),
                    })
            except Exception as e:
                logger.warning("VectorStore.search failed: %s", e)

        return results

    def get_user_preferences(self) -> list[dict[str, Any]]:
        """ユーザーの好み・興味を検索する。"""
        return self.search_semantic("ユーザーの好み 興味 趣味", max_results=5)

    # ── 記録 ──────────────────────────────────────────────

    def add_episodic(
        self,
        content: str,
        kind: str = "user_input",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """エピソード記憶に追加する。

        Args:
            content: 記憶の内容
            kind: 種別（'user_input', 'assistant', 'proactive', 'system'）
            metadata: 追加メタデータ
        """
        # EpisodicStore.add() は summary: str を受け取る
        summary = content
        if metadata:
            summary = f"{content} [metadata: {metadata}]"
        self._episodic.add(summary)

    def add_semantic(self, content: str, tags: list[str] | None = None) -> None:
        """意味記憶（教訓・好み）に追加する。

        Args:
            content: 記憶の内容
            tags: タグ一覧
        """
        entry: dict[str, Any] = {"content": content}
        if tags:
            entry["tags"] = tags
        self._semantic.add(entry)

    def add_semantic_by_type(
        self,
        entry_type: str,
        content: str,
        tags: list[str] | None = None,
    ) -> None:
        """種別付きで意味記憶に追加する。

        Args:
            entry_type: 'lesson' | 'preference' | 'warning' | 'trait'
            content: 記憶の内容
            tags: タグ一覧
        """
        entry: dict[str, Any] = {"content": content, "type": entry_type}
        if tags:
            entry["tags"] = tags
        self._semantic.add(entry)

    # ── 取得 ──────────────────────────────────────────────

    def get_recent(self, n: int = 3) -> list[dict[str, Any]]:
        """直近のエピソード記憶を取得する。

        Returns:
            時系列順（新しい順）のエピソード記憶リスト（辞書形式）
        """
        summaries = self._episodic.get_recent(n)
        return [{"summary": s} for s in summaries]

    # ── ユーティリティ ────────────────────────────────────

    @staticmethod
    def _simple_score(query: str, content: str) -> float:
        """単純なキーワード一致スコア（0.0〜1.0）。フォールバック用。"""
        query_words = set(query.lower().split())
        content_words = set(content.lower().split())
        if not query_words:
            return 0.0
        return min(len(query_words & content_words) / max(len(query_words), 1), 1.0)
