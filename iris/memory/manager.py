from __future__ import annotations

import logging
import time
from typing import Any

from iris.event.event_bus import EventBus
from iris.event.event_types import InputReady, InputReceived, TimerTick
from iris.kernel.config import ProactiveConfig
from iris.memory.sensory.buffer import InputBuffer
from iris.memory.stores import EpisodicStore, SemanticStore
from iris.memory.vector_store import VectorStore

MemoryStream = str

logger = logging.getLogger(__name__)


class MemoryManager:
    def __init__(
        self,
        event_bus: EventBus,
        episodic: EpisodicStore,
        semantic: SemanticStore | None = None,
        vector_store: VectorStore | None = None,
        proactive_config: ProactiveConfig | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._episodic = episodic
        self._semantic = semantic
        self._vector_store = vector_store
        self._sensory_buffer: InputBuffer | None = None
        self._last_proactive_check: float = 0.0
        self._proactive_config = proactive_config

        self._event_bus.subscribe("InputReceived", self._on_input_received)
        if proactive_config and proactive_config.enabled:
            self._event_bus.subscribe("TimerTick", self._on_timer_tick)

    def set_sensory_buffer(self, buffer: InputBuffer) -> None:
        self._sensory_buffer = buffer
        self._sensory_buffer.set_flush_callback(self._on_sensory_flush)

    # === TimerTick handler (rate-limit → forward) ===

    def _on_timer_tick(self, _event: TimerTick) -> None:
        cfg = self._proactive_config
        if not cfg or not cfg.enabled:
            return
        now = time.time()
        if now - self._last_proactive_check < cfg.check_interval_sec:
            return
        self._last_proactive_check = now
        self._event_bus.publish(
            InputReady(
                timestamp=None,
                source="memory",
                session_id="",
                content="",
                context={"from_timer": True},
            )
        )

    # === EventBus handlers ===

    def _on_input_received(self, event: InputReceived) -> None:
        buf = self._sensory_buffer
        if buf is not None:
            buf.session_id = event.session_id
            buf.add_fragment(event.content, event.is_final)
        else:
            self._episodic.add(f"[{event.msg_type}] {event.content}")
            self._event_bus.publish(
                InputReady(
                    timestamp=event.timestamp,
                    source="memory",
                    session_id=event.session_id,
                    content=event.content,
                )
            )

    def _on_sensory_flush(self, session_id: str, content: str) -> None:
        if content:
            self._episodic.add(f"[user_input] {content}")
        self._event_bus.publish(
            InputReady(
                timestamp=None,
                source="memory",
                session_id=session_id,
                content=content,
            )
        )

    # === Generic API ===

    def store(self, stream: MemoryStream, data: dict) -> None:
        if stream == "episodic":
            summary = data.get("content", "")
            kind = data.get("kind", "")
            if kind:
                summary = f"[{kind}] {summary}"
            self._episodic.add(summary)
        elif stream == "semantic" and self._semantic:
            self._semantic.add(data)
        else:
            logger.warning("MemoryManager: unknown stream=%s", stream)

    def retrieve(self, stream: MemoryStream, **filters) -> list[dict]:
        if stream == "episodic":
            n = filters.get("n", 5)
            summaries = self._episodic.get_recent(n)
            return [{"summary": s} for s in summaries]
        elif stream == "sensory" and self._sensory_buffer:
            return [{"text": self._sensory_buffer.accumulated_text}]
        return []

    def search(self, query: str, stream: MemoryStream | None = None, **kwargs) -> list[dict]:
        if stream == "semantic" or (stream is None and self._semantic):
            assert self._semantic is not None
            results = self._semantic.search(query=query, max_results=kwargs.get("max_results", 3))
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
        if self._vector_store:
            results = self._vector_store.search(query=query, max_results=kwargs.get("max_results", 3))
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
        return []

    def clear(self, stream: MemoryStream | None = None) -> None:
        if stream == "episodic" or stream is None:
            self._episodic.clear()
        if (stream == "semantic" or stream is None) and self._semantic:
            self._semantic.clear()
        if stream == "sensory" and self._sensory_buffer:
            self._sensory_buffer.close()

    # === Backward compat API (for LLMPipeline) ===

    def get_user_preferences(self) -> list[dict[str, Any]]:
        return self.search("ユーザーの好み 興味 趣味", stream="semantic", max_results=2)

    def add_episodic(self, content: str, kind: str = "", _metadata: dict | None = None) -> None:
        self.store("episodic", {"content": content, "kind": kind})

    def get_recent(self, n: int = 3) -> list[dict[str, Any]]:
        return self.retrieve("episodic", n=n)

    def add_semantic(self, content: str, tags: list[str] | None = None) -> None:
        self.store("semantic", {"content": content, "tags": tags or []})

    def add_semantic_by_type(self, entry_type: str, content: str, tags: list[str] | None = None) -> None:
        self.store("semantic", {"content": content, "type": entry_type, "tags": tags or []})

    def search_semantic(self, query: str, max_results: int = 3) -> list[dict[str, Any]]:
        return self.search(query, stream="semantic", max_results=max_results)
