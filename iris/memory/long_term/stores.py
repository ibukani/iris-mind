from __future__ import annotations

from datetime import UTC, datetime
import json
import logging
from pathlib import Path
import time
from typing import Protocol

from iris.memory.long_term.vector_store import VectorStore

logger = logging.getLogger(__name__)


class AgentsMdStoreProtocol(Protocol):
    def load(self) -> str: ...
    def update(self, new_content: str) -> None: ...


class EpisodicStoreProtocol(Protocol):
    def add(self, summary: str) -> None: ...
    def get_recent(self, n: int = 5) -> list[dict]: ...
    def clear(self) -> None: ...


class SemanticStoreProtocol(Protocol):
    def add(self, entry: dict) -> None: ...
    def search(self, query: str, max_results: int = 3) -> list[dict]: ...
    def clear(self) -> None: ...


class AgentsMdStore:
    """構造記憶。.iris/data/iris_profile.mdの読み書き。"""

    def __init__(self, path: str = ".iris/data/iris_profile.md", max_bytes: int = 2048, cache_ttl: float = 10.0):
        self.path = Path(path)
        self.max_bytes = max_bytes
        self._cache: str | None = None
        self._cache_time: float = 0
        self._cache_ttl: float = cache_ttl

    def load(self) -> str:
        now = time.time()
        if self._cache is not None and (now - self._cache_time) < self._cache_ttl:
            return self._cache
        if self.path.exists():
            self._cache = self.path.read_text(encoding="utf-8")
            self._cache_time = now
            return self._cache
        return ""

    def update(self, new_content: str) -> None:
        if len(new_content.encode("utf-8")) > self.max_bytes:
            new_content = self._truncate(new_content)
        self.path.write_text(new_content, encoding="utf-8")
        self._cache = new_content
        self._cache_time = time.time()
        logger.info("AgentsMdStore: updated (%d bytes)", len(new_content.encode("utf-8")))

    def _truncate(self, content: str) -> str:
        lines = content.split("\n")
        sizes = [len(line.encode("utf-8")) + 1 for line in lines]
        total = sum(sizes)
        while len(lines) > 1 and total > self.max_bytes:
            last = sizes.pop()
            total -= last
            lines.pop()
        return "\n".join(lines)


class EpisodicStore:
    """エピソード記憶。上限到達時は古いものを削除。"""

    def __init__(self, path: str = ".iris/data/episodes.jsonl", max_entries: int = 30):
        self.path = Path(path)
        self.max_entries = max_entries

    def clear(self) -> None:
        if self.path.exists():
            self.path.unlink()
        logger.info("EpisodicStore: cleared")

    def add(self, summary: str, metadata: dict | None = None) -> None:
        entries = self._load_all()
        entry: dict[str, object] = {"summary": summary, "timestamp": datetime.now(UTC).isoformat()}
        if metadata:
            entry["metadata"] = metadata
        entries.append(entry)
        if len(entries) > self.max_entries:
            entries = entries[-self.max_entries :]
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(
            "\n".join(json.dumps(e) for e in entries),
            encoding="utf-8",
        )
        tmp.replace(self.path)
        logger.info("EpisodicStore: added entry, total=%d", len(entries))

    def get_recent(self, n: int = 5) -> list[dict]:
        entries = self._load_all()
        return entries[-n:]

    def _load_all(self) -> list[dict]:
        if not self.path.exists():
            return []
        entries: list[dict] = []
        for line in self.path.read_text(encoding="utf-8").strip().split("\n"):
            if not line.strip():
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                logger.warning("EpisodicStore: skipping corrupt entry: %.80s", line)
        return entries


class SemanticStore:
    """意味記憶。JSONL永続化 + VectorStore によるハイブリッド検索。"""

    def __init__(
        self,
        path: str = ".iris/data/semantic.jsonl",
        max_entries: int = 100,
        vector_db_path: str = ".iris/data/chroma_db",
    ):
        self.path = Path(path)
        self.max_entries = max_entries
        self.vector = VectorStore(path=vector_db_path)
        self._synced_count = 0

    def sync(self) -> None:
        entries = self._load_all()
        unsynced = len(entries) - self._synced_count
        if unsynced <= 0:
            return
        for e in entries[self._synced_count :]:
            self.vector.add(e)
        self._synced_count = len(entries)
        logger.info("SemanticStore: synced %d entries to vector store", unsynced)

    def add(self, entry: dict) -> None:
        entries = self._load_all()
        if self._is_duplicate(entry.get("content", ""), entries):
            return
        entry["id"] = f"lesson_{len(entries) + 1:03d}"
        entry.setdefault("timestamp", "")
        entry.setdefault("tags", [])
        entry.setdefault("type", "lesson")
        entries.append(entry)
        if len(entries) > self.max_entries:
            entries = entries[-self.max_entries :]
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(
            "\n".join(json.dumps(e) for e in entries),
            encoding="utf-8",
        )
        tmp.replace(self.path)
        self.vector.add(entry)
        self._synced_count = len(entries)
        logger.info("SemanticStore: added entry, total=%d type=%s", len(entries), entry.get("type", "unknown"))

    def clear(self) -> None:
        if self.path.exists():
            self.path.unlink()
        self.vector.clear()
        self._synced_count = 0
        logger.info("SemanticStore: cleared")

    def search(self, query: str, max_results: int = 3) -> list[dict]:
        return self.vector.search(query, max_results=max_results)

    def _load_all(self) -> list[dict]:
        if not self.path.exists():
            return []
        entries: list[dict] = []
        for line in self.path.read_text(encoding="utf-8").strip().split("\n"):
            if not line.strip():
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                logger.warning("SemanticStore: skipping corrupt entry: %.80s", line)
        return entries

    def _is_duplicate(self, content: str, entries: list[dict]) -> bool:
        return any(e.get("content") == content for e in entries)
