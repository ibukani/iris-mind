from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
import threading
import time
from typing import Protocol

from loguru import logger

from iris.memory.long_term.vector_store import VectorStore


class AgentsMdStoreProtocol(Protocol):
    def load(self) -> str: ...
    def update(self, new_content: str) -> None: ...


class EpisodicStoreProtocol(Protocol):
    @property
    def max_entries(self) -> int: ...
    def add(self, summary: str, metadata: dict | None = None) -> None: ...
    def get_recent(self, n: int = 5) -> list[dict]: ...
    def clear(self) -> None: ...
    def load_all(self) -> list[dict]: ...


class SemanticStoreProtocol(Protocol):
    def add(self, entry: dict) -> None: ...
    def search(self, query: str, max_results: int = 3) -> list[dict]: ...
    def clear(self) -> None: ...
    def load_all(self) -> list[dict]: ...


class _JsonlStore:
    """JSONLファイルの読み書きを提供する基底クラス。

    なぜこの設計にしたか:
    EpisodicStoreとSemanticStoreで重複していたJSONL入出力を統合し、
    ファイル操作の一貫性を保ちながら保守箇所を一箇所に閉じるため。
    """

    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()

    def load_all(self) -> list[dict]:
        if not self.path.exists():
            return []
        entries: list[dict] = []
        for line in self.path.read_text(encoding="utf-8").strip().split("\n"):
            if not line.strip():
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                logger.warning("%s: skipping corrupt entry: %.80s", type(self).__name__, line)
        return entries

    def _write_file(self, entries: list[dict]) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(
            "\n".join(json.dumps(e) for e in entries),
            encoding="utf-8",
        )
        self._replace_atomic(tmp)

    def _replace_atomic(self, src: Path) -> None:
        for attempt in range(3):
            try:
                src.replace(self.path)
                return
            except PermissionError:
                if attempt == 2:
                    raise
                time.sleep(0.05 * (attempt + 1))


class AgentsMdStore:
    """構造記憶。.iris/config/iris_profile.mdの読み込み（書き込み禁止）。"""

    def __init__(self, path: str = ".iris/config/iris_profile.md", max_bytes: int = 2048, cache_ttl: float = 10.0):
        self.path = Path(path)
        self.max_bytes = max_bytes
        self._cache: str | None = None
        self._cache_mtime: float | None = None

    def load(self) -> str:
        if self.path.exists():
            try:
                mtime = self.path.stat().st_mtime
            except OSError:
                mtime = None

            if self._cache is not None and self._cache_mtime == mtime:
                return self._cache

            try:
                self._cache = self.path.read_text(encoding="utf-8")
                self._cache_mtime = mtime
            except Exception as e:
                logger.warning("AgentsMdStore: failed to load file: %s", e)
                if self._cache is not None:
                    return self._cache
                return ""
            return self._cache
        return ""

    def update(self, new_content: str) -> None:
        if len(new_content.encode("utf-8")) > self.max_bytes:
            new_content = self._truncate(new_content)
        self.path.write_text(new_content, encoding="utf-8")
        self._cache = new_content
        try:
            self._cache_mtime = self.path.stat().st_mtime
        except OSError:
            self._cache_mtime = None
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


class EpisodicStore(_JsonlStore):
    """エピソード記憶。上限到達時は古いものを削除。"""

    def __init__(self, path: str = ".iris/data/episodes.jsonl", max_entries: int = 30):
        super().__init__(path)
        self.max_entries = max_entries

    def clear(self) -> None:
        if self.path.exists():
            self.path.unlink()
        logger.info("EpisodicStore: cleared")

    def add(self, summary: str, metadata: dict | None = None) -> None:
        with self._lock:
            entries = self.load_all()
            entry: dict[str, object] = {"summary": summary, "timestamp": datetime.now(UTC).isoformat()}
            if metadata:
                entry["metadata"] = metadata
            entries.append(entry)
            if len(entries) > self.max_entries:
                entries = entries[-self.max_entries :]
            self._write_file(entries)
            logger.info("EpisodicStore: added entry, total=%d", len(entries))

    def get_recent(self, n: int = 5) -> list[dict]:
        entries = self.load_all()
        return entries[-n:]


class SemanticStore(_JsonlStore):
    """意味記憶。JSONL永続化 + VectorStore によるハイブリッド検索。"""

    def __init__(
        self,
        path: str = ".iris/data/semantic.jsonl",
        max_entries: int = 100,
        vector_db_path: str = ".iris/data/chroma_db",
    ):
        super().__init__(path)
        self.max_entries = max_entries
        self.vector = VectorStore(path=vector_db_path)
        self._synced_count = 0

    def sync(self) -> None:
        entries = self.load_all()
        unsynced = len(entries) - self._synced_count
        if unsynced <= 0:
            return
        for e in entries[self._synced_count :]:
            self.vector.add(e)
        self._synced_count = len(entries)
        logger.info("SemanticStore: synced %d entries to vector store", unsynced)

    def add(self, entry: dict) -> None:
        with self._lock:
            entries = self.load_all()
            if self._is_duplicate(entry.get("content", ""), entries):
                return
            entry["id"] = f"lesson_{len(entries) + 1:03d}"
            entry.setdefault("timestamp", "")
            entry.setdefault("tags", [])
            entry.setdefault("type", "lesson")
            entries.append(entry)
            if len(entries) > self.max_entries:
                entries = entries[-self.max_entries :]
            self._write_file(entries)
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

    def _is_duplicate(self, content: str, entries: list[dict]) -> bool:
        return any(e.get("content") == content for e in entries)
