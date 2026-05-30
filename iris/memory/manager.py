from __future__ import annotations

from collections.abc import Callable
from typing import Any

from loguru import logger

from iris.memory.dispatcher import (
    build_store_handlers,
    dispatch_clear,
    dispatch_retrieve,
    dispatch_search,
)
from iris.memory.long_term.goal_store import GoalStore
from iris.memory.models import blocks_text


class MemoryManager:
    """記憶マネージャー — 各記憶種別の管理クラスへのディスパッチャ。

    脳科学に基づく3層構造:
    - SensoryMemoryManager   (感覚記憶): 生入力の一時保持
    - ShortTermMemoryManager (短期記憶): 現在の会話内容（ワーキングメモリ）
    - LongTermMemoryManager  (長期記憶): エピソード記憶 + 意味記憶

    このクラスは以下を責務とする:
    1. イベント処理 (pending / timer / InputReady)
    2. store() / retrieve() / search() / clear() のディスパッチ
    3. 後方互換 API (add_episodic, get_recent, 等)
    """

    def __init__(
        self,
        *,
        sensory: Any | None = None,
        short_term: Any | None = None,
        long_term: Any | None = None,
    ) -> None:
        from iris.memory.long_term.manager import LongTermMemoryManager
        from iris.memory.sensory.manager import SensoryMemoryManager
        from iris.memory.short_term.manager import ShortTermMemoryManager

        self.sensory: Any = sensory or SensoryMemoryManager()
        self.short_term: Any = short_term or ShortTermMemoryManager()
        self.long_term: Any = long_term or LongTermMemoryManager()
        self.goals: GoalStore = GoalStore()

        self._store_handlers: dict[str, Callable[[Any], None]] = build_store_handlers(
            self.sensory,
            self.short_term,
            self.long_term,
        )

    def get_state(self) -> dict:
        from iris.memory.protocol import safe_count

        episodic_count = safe_count(self.long_term.episodic) if self.long_term else 0
        semantic_count = safe_count(self.long_term.semantic) if self.long_term else 0
        return {
            "episodic": episodic_count,
            "semantic": semantic_count,
            "short_term_turns": self.short_term.turn_count if self.short_term else 0,
        }

    def set_sensory_buffer(self, buf: Any) -> None:
        self.sensory = buf

    def store(self, stream: str, data: Any, room_id: str = "", account_id: str = "") -> None:
        logger.info("MemoryManager: store stream={}", stream)
        if isinstance(data, dict):
            if room_id:
                data.setdefault("room_id", room_id)
            if account_id:
                data.setdefault("account_id", account_id)
        handler = self._store_handlers.get(stream)
        if handler is not None:
            handler(data)
        else:
            logger.warning("MemoryManager: unknown stream={}", stream)

    def retrieve(self, stream: str, room_id: str = "", account_id: str = "", **filters: Any) -> list[dict[str, Any]]:
        return dispatch_retrieve(
            stream, filters, self.sensory, self.short_term, self.long_term, room_id=room_id, account_id=account_id
        )

    def search(
        self, query: str, stream: str | None = None, room_id: str = "", account_id: str = "", **kwargs: Any
    ) -> list[dict[str, Any]]:
        return dispatch_search(
            query, stream, kwargs, self.short_term, self.long_term, room_id=room_id, account_id=account_id
        )

    def clear(self, stream: str | None = None, room_id: str = "") -> None:
        dispatch_clear(stream, self.sensory, self.short_term, self.long_term)

    def flush(self, room_id: str = "", account_id: str = "") -> None:
        """未定着の短期記憶を長期記憶に書き出してからクリアする。"""
        unconsolidated = self.short_term.get_unconsolidated_turns(account_id=account_id)
        if not unconsolidated:
            return

        user_turns = [t for t in unconsolidated if t.get("role") == "user"]
        if user_turns:
            combined = " | ".join(blocks_text(t.get("blocks", []))[:100] for t in user_turns[-3:])
            self.long_term.store_episodic(
                {"content": f"[conversation] {combined}", "kind": "conversation"},
                room_id=room_id,
                account_id=account_id,
            )

        topics = self.short_term.current_topics
        for topic in topics:
            self.long_term.store_semantic(
                {"content": topic, "type": "topic", "tags": ["short_term_topic"]},
                room_id=room_id,
                account_id=account_id,
            )

        self.short_term.mark_consolidated()
        logger.info("MemoryManager: flushed {} turns, {} topics", len(unconsolidated), len(topics))

    def get_user_preferences(self, room_id: str = "", account_id: str = "") -> list[dict[str, Any]]:
        return self.long_term.search_semantic(
            "ユーザーの好み 興味 趣味", max_results=2, room_id=room_id, account_id=account_id
        )  # type: ignore[no-any-return]

    def add_episodic(
        self, content: str, kind: str = "", room_id: str = "", account_id: str = "", _metadata: dict | None = None
    ) -> None:
        self.store("episodic", {"content": content, "kind": kind}, room_id=room_id, account_id=account_id)

    def get_recent(self, n: int = 3, room_id: str = "", account_id: str = "") -> list[dict[str, Any]]:
        return self.long_term.get_episodic_recent(n, room_id=room_id, account_id=account_id)  # type: ignore[no-any-return]

    def add_semantic(
        self, content: str, tags: list[str] | None = None, room_id: str = "", account_id: str = ""
    ) -> None:
        self.store("semantic", {"content": content, "tags": tags or []}, room_id=room_id, account_id=account_id)

    def add_semantic_by_type(
        self, entry_type: str, content: str, tags: list[str] | None = None, room_id: str = "", account_id: str = ""
    ) -> None:
        self.store(
            "semantic",
            {"content": content, "type": entry_type, "tags": tags or []},
            room_id=room_id,
            account_id=account_id,
        )

    def search_semantic(
        self, query: str, max_results: int = 3, room_id: str = "", account_id: str = ""
    ) -> list[dict[str, Any]]:
        return self.long_term.search_semantic(query, max_results=max_results, room_id=room_id, account_id=account_id)  # type: ignore[no-any-return]

    def search_emotional(
        self,
        current_emotion: Any | None = None,
        max_results: int = 5,
    ) -> list[dict[str, Any]]:
        return self.long_term.search_emotional(  # type: ignore[no-any-return]
            current_emotion=current_emotion,
            max_results=max_results,
        )
