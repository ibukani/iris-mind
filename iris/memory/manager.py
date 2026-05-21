from __future__ import annotations

from contextlib import suppress
import logging
import threading
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from iris.event.event_bus import EventBus
    from iris.kernel.config import ProactiveConfig
    from iris.limbic.models import EmotionState

from iris.event.event_types import ClientSessionEvent, InputReady, MessageEvent, TimerTick
from iris.memory.long_term.manager import LongTermMemoryManager, LongTermMemoryProtocol
from iris.memory.long_term.stores import EpisodicStore, SemanticStore
from iris.memory.long_term.vector_store import VectorStore
from iris.memory.sensory.manager import SensoryMemoryManager, SensoryMemoryProtocol
from iris.memory.short_term.manager import ShortTermMemoryManager, ShortTermMemoryProtocol

logger = logging.getLogger(__name__)


class MemoryManagerProtocol(Protocol):
    """記憶オーケストレーションマネージャーのインターフェース。

    なぜこの設計にしたか:
    他の脳機能レイヤー（Agency等）が具象クラスである MemoryManager に直接依存するのを防ぎ、
    モック化や代替実装を容易にするため。
    """

    def set_sensory_buffer(self, buf: SensoryMemoryProtocol) -> None: ...
    def store(self, stream: str, data: Any) -> None: ...
    def retrieve(self, stream: str, **filters: Any) -> list[dict]: ...
    def search(self, query: str, stream: str | None = None, **kwargs: Any) -> list[dict]: ...
    def clear(self, stream: str | None = None) -> None: ...
    def flush(self) -> None: ...
    def get_user_preferences(self) -> list[dict[str, Any]]: ...
    def add_episodic(self, content: str, kind: str = "", _metadata: dict | None = None) -> None: ...
    def get_recent(self, n: int = 3) -> list[dict[str, Any]]: ...
    def add_semantic(self, content: str, tags: list[str] | None = None) -> None: ...
    def add_semantic_by_type(self, entry_type: str, content: str, tags: list[str] | None = None) -> None: ...
    def search_semantic(self, query: str, max_results: int = 3) -> list[dict[str, Any]]: ...
    def search_emotional(
        self,
        current_emotion: EmotionState | None = None,
        max_results: int = 5,
    ) -> list[dict[str, Any]]: ...

    @property
    def short_term(self) -> ShortTermMemoryProtocol: ...
    @property
    def long_term(self) -> LongTermMemoryProtocol: ...


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
        episodic: EpisodicStore | None = None,
        semantic: SemanticStore | None = None,
        vector_store: VectorStore | None = None,
        sensory: SensoryMemoryProtocol | None = None,
        short_term: ShortTermMemoryProtocol | None = None,
        long_term: LongTermMemoryProtocol | None = None,
        proactive_config: ProactiveConfig | None = None,
    ) -> None:
        self.sensory: SensoryMemoryProtocol = sensory or SensoryMemoryManager()
        self.short_term: ShortTermMemoryProtocol = short_term or ShortTermMemoryManager()
        self.long_term: LongTermMemoryProtocol = long_term or LongTermMemoryManager(
            episodic=episodic,
            semantic=semantic,
            vector_store=vector_store,
        )

        self._event_bus: EventBus | None = event_bus
        self._proactive_config: ProactiveConfig | None = proactive_config
        self._pending_input: dict[str, str] = {}
        self._pending_lock: threading.Lock = threading.Lock()

        if event_bus is not None:
            event_bus.subscribe("MessageEvent", self._on_message_event)
            event_bus.subscribe("TimerTick", self._on_timer_tick)
            event_bus.subscribe("ClientSessionEvent", self._on_client_session_event)

    def get_state(self) -> dict:
        episodic_count = 0
        semantic_count = 0
        lt = self.long_term
        if lt is not None:
            if hasattr(lt, "episodic") and lt.episodic:
                with suppress(Exception):
                    episodic_count = len(lt.episodic.load_all())
            if hasattr(lt, "semantic") and lt.semantic:
                with suppress(Exception):
                    semantic_count = len(lt.semantic.load_all())
        return {
            "episodic": episodic_count,
            "semantic": semantic_count,
            "short_term_turns": self.short_term.turn_count if self.short_term else 0,
        }

    def set_sensory_buffer(self, buf: SensoryMemoryProtocol) -> None:
        self.sensory = buf

    def _on_message_event(self, event: MessageEvent) -> None:
        if not event.content:
            return
        if event.direction not in ("request", "event") or event.msg_type not in ("chat", "system"):
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
        if self._event_bus is None:
            return
        with self._pending_lock:
            pending = dict(self._pending_input)
            self._pending_input.clear()

        if pending:
            for session_id, content in pending.items():
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

    def _on_client_session_event(self, event: ClientSessionEvent) -> None:
        if event.action != "connected":
            return
        if self._event_bus is None:
            return

        logger.info(
            "MemoryManager: client connected session=%s role=%s offline_duration=%s",
            event.session_id,
            event.role,
            event.offline_duration,
        )
        self._event_bus.publish(
            InputReady(
                timestamp=None,
                source="memory",
                session_id=event.session_id,
                content="",
                context={
                    "system_event": event.action,
                    "offline_duration": event.offline_duration,
                    "role": event.role,
                    "identity": event.identity,
                },
            )
        )

    def store(self, stream: str, data: Any) -> None:
        logger.info("MemoryManager: store stream=%s", stream)
        if stream == "sensory":
            if isinstance(data, dict) and data.get("raw"):
                self.sensory.store_raw(data["raw"])
            else:
                self.sensory.add_fragment(str(data), is_final=True)
            return

        if stream == "short_term":
            if isinstance(data, str):
                self.short_term.add_turn("system", data)
            elif isinstance(data, dict):
                role = data.get("role", "system")
                content = data.get("content") or data.get("summary") or str(data)
                self.short_term.add_turn(role, content)
            return

        if stream == "episodic":
            self.long_term.store_episodic(data)
            if isinstance(data, dict):
                self.short_term.add_turn(
                    "system",
                    data.get("content") or data.get("summary") or str(data),
                )
            return

        if stream == "semantic":
            self.long_term.store_semantic(data)
            if isinstance(data, dict):
                content = data.get("content", "")
                if content:
                    self.short_term.add_turn("system", content)
            return

        logger.warning("MemoryManager: unknown stream=%s", stream)

    def retrieve(self, stream: str, **filters: Any) -> list[dict]:
        if stream == "sensory":
            result = self.sensory.retrieve()
            return [result] if result else []
        if stream == "short_term":
            n = filters.get("n", 5) if isinstance(filters.get("n"), int) else 5
            return self.short_term.get_recent_turns(n)
        if stream == "episodic":
            n = filters.get("n", 5) if isinstance(filters.get("n"), int) else 5
            return self.long_term.get_episodic_recent(n)
        return []

    def search(self, query: str, stream: str | None = None, **kwargs: Any) -> list[dict]:
        max_results = kwargs.get("max_results", 3) if isinstance(kwargs.get("max_results"), int) else 3
        if stream == "short_term":
            return self.short_term.search(query, max_results=max_results)
        if stream == "semantic" or stream is None:
            return self.long_term.search_semantic(query, max_results=max_results)
        return []

    def clear(self, stream: str | None = None) -> None:
        logger.info("MemoryManager: clear stream=%s", stream or "all")
        if stream == "sensory" or stream is None:
            self.sensory.clear()
        if stream == "short_term" or stream is None:
            self.short_term.clear()
        if stream == "episodic" or stream is None:
            self.long_term.clear_episodic()
        if stream == "semantic" or stream is None:
            self.long_term.clear_semantic()

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
        logger.info("MemoryManager: flushed %d turns, %d topics", len(unconsolidated), len(topics))

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
