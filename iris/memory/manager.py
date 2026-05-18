from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from iris.limbic.models import EmotionState

from iris.event.event_types import InputReady, InputReceived, TimerTick
from iris.memory.long_term.manager import LongTermMemoryManager
from iris.memory.sensory.manager import SensoryMemoryManager
from iris.memory.short_term.manager import ShortTermMemoryManager
from iris.memory.stores import EpisodicStore, SemanticStore
from iris.memory.vector_store import VectorStore

logger = logging.getLogger(__name__)


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
        event_bus: Any = None,
        episodic: EpisodicStore | None = None,
        semantic: SemanticStore | None = None,
        vector_store: VectorStore | None = None,
        sensory: SensoryMemoryManager | None = None,
        short_term: ShortTermMemoryManager | None = None,
        long_term: LongTermMemoryManager | None = None,
        proactive_config: Any = None,
    ) -> None:
        self.sensory: SensoryMemoryManager = sensory or SensoryMemoryManager()
        self.short_term: ShortTermMemoryManager = short_term or ShortTermMemoryManager()
        self.long_term: LongTermMemoryManager = long_term or LongTermMemoryManager(
            episodic=episodic,
            semantic=semantic,
            vector_store=vector_store,
        )

        self._event_bus = event_bus
        self._proactive_config = proactive_config
        self._pending_input: dict[str, str] = {}
        self._pending_lock: threading.Lock = threading.Lock()

        if event_bus is not None:
            event_bus.subscribe("InputReceived", self._on_input_received)
            event_bus.subscribe("TimerTick", self._on_timer_tick)

    def set_sensory_buffer(self, buf: SensoryMemoryManager) -> None:
        self.sensory = buf

    def _on_input_received(self, event: InputReceived) -> None:
        if not event.content:
            return
        self.sensory.store_raw(event.content)
        with self._pending_lock:
            self._pending_input[event.session_id] = event.content
        logger.debug(
            "MemoryManager: input pending session=%s content=%.80s",
            event.session_id,
            event.content,
        )

    def _on_timer_tick(self, event: TimerTick) -> None:
        session_id = ""
        content = ""
        with self._pending_lock:
            if self._pending_input:
                session_id, content = self._pending_input.popitem()

        if content and session_id:
            self._event_bus.publish(
                InputReady(
                    timestamp=None,
                    source="memory",
                    session_id=session_id,
                    content=content,
                    context={},
                )
            )
            return

        if self._proactive_config is not None:
            self._event_bus.publish(
                InputReady(
                    timestamp=None,
                    source="memory",
                    session_id="",
                    content="",
                    context={"from_timer": True},
                )
            )

    # ============================================================
    # ディスパッチャー
    # ============================================================

    def store(self, stream: str, data: Any) -> None:
        if stream == "sensory":
            if isinstance(data, dict) and data.get("raw"):
                self.sensory.store_raw(data["raw"])
            else:
                self.sensory.add_fragment(str(data), is_final=True)
        elif stream == "short_term":
            if isinstance(data, str):
                self.short_term.add_turn("system", data)
            elif isinstance(data, dict):
                role = data.get("role", "system")
                content = data.get("content") or data.get("summary") or str(data)
                self.short_term.add_turn(role, content)
        elif stream == "episodic":
            self.long_term.store_episodic(data)
            if isinstance(data, dict):
                self.short_term.add_turn(
                    "system",
                    data.get("content") or data.get("summary") or str(data),
                )
        elif stream == "semantic":
            self.long_term.store_semantic(data)
            if isinstance(data, dict):
                content = data.get("content", "")
                if content:
                    self.short_term.add_turn("system", content)
        else:
            logger.warning("MemoryManager: unknown stream=%s", stream)

    def retrieve(self, stream: str, **filters: Any) -> list[dict]:
        if stream == "sensory":
            result = self.sensory.retrieve()
            return [result] if result else []
        if stream == "short_term":
            n = filters.get("n", 5)
            if not isinstance(n, int):
                n = 5
            return self.short_term.get_recent_turns(n)
        if stream == "episodic":
            n = filters.get("n", 5)
            if not isinstance(n, int):
                n = 5
            return self.long_term.get_episodic_recent(n)
        return []

    def search(self, query: str, stream: str | None = None, **kwargs: Any) -> list[dict]:
        max_results = kwargs.get("max_results", 3)
        if not isinstance(max_results, int):
            max_results = 3
        if stream == "semantic" or stream is None:
            return self.long_term.search_semantic(query, max_results=max_results)
        return []

    def clear(self, stream: str | None = None) -> None:
        if stream == "sensory" or stream is None:
            self.sensory.clear()
        if stream == "short_term" or stream is None:
            self.short_term.clear()
        if stream == "episodic" or stream is None:
            self.long_term.clear_episodic()
        if stream == "semantic" or stream is None:
            self.long_term.clear_semantic()

    # ============================================================
    # 後方互換 API
    # ============================================================

    def get_user_preferences(self) -> list[dict[str, Any]]:
        return self.long_term.search_semantic("ユーザーの好み 興味 趣味", max_results=2)

    def add_episodic(self, content: str, kind: str = "", _metadata: dict | None = None) -> None:
        self.store("episodic", {"content": content, "kind": kind})

    def get_recent(self, n: int = 3) -> list[dict[str, Any]]:
        return self.long_term.get_episodic_recent(n)

    def add_semantic(self, content: str, tags: list[str] | None = None) -> None:
        self.store("semantic", {"content": content, "tags": tags or []})

    def add_semantic_by_type(self, entry_type: str, content: str, tags: list[str] | None = None) -> None:
        self.store("semantic", {"content": content, "type": entry_type, "tags": tags or []})

    def search_semantic(self, query: str, max_results: int = 3) -> list[dict[str, Any]]:
        return self.long_term.search_semantic(query, max_results=max_results)

    def search_emotional(
        self,
        current_emotion: EmotionState | None = None,
        max_results: int = 5,
    ) -> list[dict[str, Any]]:
        return self.long_term.search_emotional(
            current_emotion=current_emotion,
            max_results=max_results,
        )
