from __future__ import annotations

import logging
from typing import Any

from iris.memory.sensory.buffer import InputBuffer
from iris.memory.stores import EpisodicStore, SemanticStore
from iris.memory.vector_store import VectorStore

logger = logging.getLogger(__name__)


class MemoryManager:
    def __init__(
        self,
        *,
        event_bus: Any = None,
        episodic: EpisodicStore | None = None,
        semantic: SemanticStore | None = None,
        vector_store: VectorStore | None = None,
        proactive_config: Any = None,
    ) -> None:
        self._event_bus = event_bus
        self._episodic = episodic
        self._semantic = semantic
        self._vector_store = vector_store
        self._proactive_config = proactive_config
        self._sensory_buffer: InputBuffer | None = None

    def set_sensory_buffer(self, buf: InputBuffer) -> None:
        self._sensory_buffer = buf

    def store(self, stream: str, data: Any) -> None:
        if stream == "sensory" and self._sensory_buffer:
            if isinstance(data, str):
                self._sensory_buffer.add_fragment(data, is_final=True)
            elif isinstance(data, dict) and "text" in data:
                self._sensory_buffer.add_fragment(data["text"], is_final=True)
        elif stream == "episodic" and self._episodic:
            summary = ""
            kind = ""
            if isinstance(data, str):
                summary = data
            elif isinstance(data, dict):
                summary = data.get("content") or data.get("summary") or str(data)
                kind = data.get("kind", "")

            if kind:
                summary = f"[{kind}] {summary}"
            self._episodic.add(summary)
        elif stream == "semantic" and self._semantic:
            self._semantic.add(data)
        else:
            logger.warning("MemoryManager: unknown stream=%s", stream)

    def retrieve(self, stream: str, **filters: Any) -> list[dict]:
        if stream == "episodic" and self._episodic:
            n = filters.get("n", 5)
            if not isinstance(n, int):
                n = 5
            return self._episodic.get_recent(n)
        if stream == "sensory" and self._sensory_buffer:
            return [{"text": self._sensory_buffer.accumulated_text}]
        return []

    def search(self, query: str, stream: str | None = None, **kwargs: Any) -> list[dict]:
        max_results = kwargs.get("max_results", 3)
        if not isinstance(max_results, int):
            max_results = 3

        if stream == "semantic" or (stream is None and self._semantic):
            if self._semantic is not None:
                results = self._semantic.search(query=query, max_results=max_results)
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
            results = self._vector_store.search(query=query, max_results=max_results)
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

    def clear(self, stream: str | None = None) -> None:
        if (stream == "episodic" or stream is None) and self._episodic:
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
