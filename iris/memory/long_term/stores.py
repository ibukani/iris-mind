from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from loguru import logger

from iris.memory.base import _JsonlStore
from iris.memory.long_term.vector_store import VectorStore


class AgentsMdStore:
    """構造記憶。.iris/config/iris_profile.mdの読み込み（書き込み禁止）。"""

    def __init__(self, path: str = ".iris/config/iris_profile.md", max_bytes: int = 2048) -> None:
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
                logger.warning("AgentsMdStore: failed to load file: {}", e)
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
        logger.info("AgentsMdStore: updated ({} bytes)", len(new_content.encode("utf-8")))

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

    def __init__(self, path: str = ".iris/data/episodes.jsonl", max_entries: int = 30) -> None:
        super().__init__(path)
        self.max_entries = max_entries

    def clear(self) -> None:
        if self.path.exists():
            self.path.unlink()
        logger.info("EpisodicStore: cleared")

    def add(self, summary: str, metadata: dict | None = None, room_id: str = "", account_id: str = "") -> None:
        entry: dict[str, object] = {
            "summary": summary,
            "timestamp": datetime.now(UTC).isoformat(),
            "room_id": room_id,
            "account_id": account_id,
        }
        if metadata:
            entry["metadata"] = metadata
        self._add_entry(entry, self.max_entries)
        logger.info("EpisodicStore: added entry")

    def get_recent(self, n: int = 5, room_id: str = "", account_id: str = "") -> list[dict]:
        entries = self.load_all()
        if account_id:
            entries = [e for e in entries if e.get("account_id") == account_id]
        if room_id:
            entries = [e for e in entries if e.get("room_id") == room_id]
        return entries[-n:]


class SemanticStore(_JsonlStore):
    """意味記憶。JSONL永続化 + VectorStore によるハイブリッド検索。"""

    def __init__(
        self,
        path: str = ".iris/data/semantic.jsonl",
        max_entries: int = 100,
        vector_db_path: str = ".iris/data/chroma_db",
    ) -> None:
        super().__init__(path)
        self.max_entries = max_entries
        self.vector = VectorStore(path=vector_db_path)
        self._synced_count = 0

    def sync(self) -> None:
        with self._lock:
            entries = self.load_all()
            unsynced = len(entries) - self._synced_count
            if unsynced <= 0:
                return
            for e in entries[self._synced_count :]:
                self.vector.add(e, account_id=e.get("account_id", ""))
            self._synced_count = len(entries)
            logger.info("SemanticStore: synced {} entries to vector store", unsynced)

    def add(self, entry: dict, room_id: str = "", account_id: str = "") -> None:
        with self._lock:
            entries = self.load_all()
            if self._is_duplicate(entry.get("content", ""), entries):
                return
            entry["id"] = f"lesson_{len(entries) + 1:03d}"
            entry.setdefault("timestamp", "")
            entry.setdefault("tags", [])
            entry.setdefault("type", "lesson")
            entry["room_id"] = room_id
            entry["account_id"] = account_id
            entries.append(entry)
            if len(entries) > self.max_entries:
                entries = entries[-self.max_entries :]
            self._write_file(entries)
            self.vector.add(entry, account_id=account_id)
            self._synced_count = len(entries)
            logger.info("SemanticStore: added entry, type={}", entry.get("type", "unknown"))

    def clear(self) -> None:
        if self.path.exists():
            self.path.unlink()
        self.vector.clear()
        self._synced_count = 0
        logger.info("SemanticStore: cleared")

    def search(self, query: str, max_results: int = 3, account_id: str = "") -> list[dict]:
        return self.vector.search(query, max_results=max_results, account_id=account_id)

    def _is_duplicate(self, content: str, entries: list[dict]) -> bool:
        return any(e.get("content") == content for e in entries)
