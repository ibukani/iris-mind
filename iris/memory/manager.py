import logging
from typing import Any

from iris.kernel.config import Config
from iris.memory.episodic import EpisodicMemory
from iris.memory.semantic import SemanticStore
from iris.memory.sensory import SensoryBuffer
from iris.memory.types import MemoryStream
from iris.memory.vector import VectorStore

logger = logging.getLogger(__name__)


class MemoryManager:
    """
    複数ストリーム (Sensory, Episodic, Semantic) を一括管理するクラス。
    """

    def __init__(self, config: Config) -> None:
        self.config = config
        self._episodic = EpisodicMemory(config.memory.episodic_capacity)
        self._semantic: SemanticStore | None = None
        self._vector_store: VectorStore | None = None
        if config.memory.semantic_enabled:
            self._semantic = SemanticStore(config.memory.semantic_db_path)
            self._vector_store = VectorStore(config.memory.vector_db_path)

        self._sensory_buffer: SensoryBuffer | None = None

    def open_sensory_stream(self) -> None:
        if not self._sensory_buffer:
            self._sensory_buffer = SensoryBuffer()

    def close_sensory_stream(self) -> None:
        if self._sensory_buffer:
            self._sensory_buffer.close()
            self._sensory_buffer = None

    def store(self, stream: MemoryStream, data: Any) -> None:
        if stream == "sensory" and self._sensory_buffer:
            if isinstance(data, str):
                self._sensory_buffer.add_text(data)
            elif isinstance(data, dict) and "text" in data:
                self._sensory_buffer.add_text(data["text"])
        elif stream == "episodic":
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

    def retrieve(self, stream: MemoryStream, **filters: Any) -> list[dict]:
        if stream == "episodic":
            n = filters.get("n", 5)
            if not isinstance(n, int):
                n = 5
            return self._episodic.get_recent(n)
        elif stream == "sensory" and self._sensory_buffer:
            return [{"text": self._sensory_buffer.accumulated_text}]
        return []

    def search(self, query: str, stream: MemoryStream | None = None, **kwargs: Any) -> list[dict]:
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
