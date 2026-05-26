from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from iris.event.event_bus import EventBus
    from iris.kernel.config import ProactiveConfig

from loguru import logger

from iris.memory.dispatcher import (
    build_store_handlers,
    dispatch_clear,
    dispatch_retrieve,
    dispatch_search,
)
from iris.memory.goal_store import GoalStore
from iris.memory.handler import _MemoryEventHandler


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
        event_bus: EventBus | None = None,
        sensory: Any | None = None,
        short_term: Any | None = None,
        long_term: Any | None = None,
        proactive_config: ProactiveConfig | None = None,
    ) -> None:
        from iris.memory.long_term.manager import LongTermMemoryManager
        from iris.memory.sensory.manager import SensoryMemoryManager
        from iris.memory.short_term.manager import ShortTermMemoryManager

        self.sensory: Any = sensory or SensoryMemoryManager()
        self.short_term: Any = short_term or ShortTermMemoryManager()
        self.long_term: Any = long_term or LongTermMemoryManager()
        self.goals: GoalStore = GoalStore()

        self._proactive_config: ProactiveConfig | None = proactive_config
        self._store_handlers: dict[str, Callable[[Any], None]] = build_store_handlers(
            self.sensory,
            self.short_term,
            self.long_term,
        )

        self._handler: _MemoryEventHandler | None
        if event_bus is not None:
            self._handler = _MemoryEventHandler(event_bus, self.sensory, proactive_config)
        else:
            self._handler = None

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

    def store(self, stream: str, data: Any) -> None:
        logger.info("MemoryManager: store stream={}", stream)
        handler = self._store_handlers.get(stream)
        if handler is not None:
            handler(data)
        else:
            logger.warning("MemoryManager: unknown stream={}", stream)

    def retrieve(self, stream: str, **filters: Any) -> list[dict[str, Any]]:
        return dispatch_retrieve(stream, filters, self.sensory, self.short_term, self.long_term)

    def search(self, query: str, stream: str | None = None, **kwargs: Any) -> list[dict[str, Any]]:
        return dispatch_search(query, stream, kwargs, self.short_term, self.long_term)

    def clear(self, stream: str | None = None) -> None:
        dispatch_clear(stream, self.sensory, self.short_term, self.long_term)

    def flush(self) -> None:
        """未定着の短期記憶を長期記憶に書き出してからクリアする。"""
        unconsolidated = self.short_term.get_unconsolidated_turns()
        if not unconsolidated:
            return

        user_turns = [t for t in unconsolidated if t.get("role") == "user"]
        if user_turns:
            combined = " | ".join(t["content"][:100] for t in user_turns[-3:])
            self.long_term.store_episodic(
                {"content": f"[conversation] {combined}", "kind": "conversation"},
            )

        topics = self.short_term.current_topics
        for topic in topics:
            self.long_term.store_semantic(
                {"content": topic, "type": "topic", "tags": ["short_term_topic"]},
            )

        self.short_term.mark_consolidated()
        logger.info("MemoryManager: flushed {} turns, {} topics", len(unconsolidated), len(topics))

    def get_user_preferences(self) -> list[dict[str, Any]]:
        return self.long_term.search_semantic("ユーザーの好み 興味 趣味", max_results=2)  # type: ignore[no-any-return]

    def add_episodic(self, content: str, kind: str = "", _metadata: dict | None = None) -> None:
        self.store("episodic", {"content": content, "kind": kind})

    def get_recent(self, n: int = 3) -> list[dict[str, Any]]:
        return self.long_term.get_episodic_recent(n)  # type: ignore[no-any-return]

    def add_semantic(self, content: str, tags: list[str] | None = None) -> None:
        self.store("semantic", {"content": content, "tags": tags or []})

    def add_semantic_by_type(self, entry_type: str, content: str, tags: list[str] | None = None) -> None:
        self.store("semantic", {"content": content, "type": entry_type, "tags": tags or []})

    def search_semantic(self, query: str, max_results: int = 3) -> list[dict[str, Any]]:
        return self.long_term.search_semantic(query, max_results=max_results)  # type: ignore[no-any-return]

    def search_emotional(
        self,
        current_emotion: Any | None = None,
        max_results: int = 5,
    ) -> list[dict[str, Any]]:
        return self.long_term.search_emotional(  # type: ignore[no-any-return]
            current_emotion=current_emotion,
            max_results=max_results,
        )
