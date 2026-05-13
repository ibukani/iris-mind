from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

from iris.memory.vector_store import VectorStore


class AgentsMdStoreProtocol(Protocol):
    def load(self) -> str: ...
    def update(self, new_content: str): ...


class EpisodicStoreProtocol(Protocol):
    def add(self, summary: str): ...
    def get_recent(self, n: int = 5) -> list[str]: ...
    def clear(self): ...


class SemanticStoreProtocol(Protocol):
    def add(self, entry: dict): ...
    def search(self, query: str, max_results: int = 3) -> list[dict]: ...
    def clear(self): ...


class AgentsMdStore:
    """構造記憶。memory/data/iris_profile.mdの読み書き。"""

    def __init__(self, path: str = "memory/data/iris_profile.md", max_bytes: int = 2048):
        self.path = Path(path)
        self.max_bytes = max_bytes

    def load(self) -> str:
        if self.path.exists():
            return self.path.read_text(encoding="utf-8")
        return ""

    def update(self, new_content: str):
        if len(new_content.encode("utf-8")) > self.max_bytes:
            new_content = self._truncate(new_content)
        self.path.write_text(new_content, encoding="utf-8")

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

    def __init__(self, path: str = "memory/data/episodes.jsonl", max_entries: int = 30):
        self.path = Path(path)
        self.max_entries = max_entries

    def clear(self):
        if self.path.exists():
            self.path.unlink()

    def add(self, summary: str):
        entries = self._load_all()
        entries.append({"summary": summary})
        if len(entries) > self.max_entries:
            entries = self._merge_and_trim(entries)
        self.path.write_text(
            "\n".join(json.dumps(e) for e in entries),
            encoding="utf-8",
        )

    def get_recent(self, n: int = 5) -> list[str]:
        entries = self._load_all()
        return [e["summary"] for e in entries[-n:]]

    def _merge_and_trim(self, entries: list[dict]) -> list[dict]:
        return entries[-self.max_entries:]

    def _load_all(self) -> list[dict]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").strip().split("\n") if line.strip()]


class SemanticStore:
    """意味記憶。JSONL永続化 + VectorStore によるハイブリッド検索。"""

    def __init__(
        self,
        path: str = "memory/data/semantic.jsonl",
        max_entries: int = 100,
        vector_db_path: str = "memory/data/chroma_db",
    ):
        self.path = Path(path)
        self.max_entries = max_entries
        self.vector = VectorStore(path=vector_db_path)
        self._synced_count = self.vector.count()
        self._sync_from_jsonl()

    def _sync_from_jsonl(self):
        entries = self._load_all()
        if len(entries) <= self._synced_count:
            return
        for e in entries[self._synced_count:]:
            self.vector.add(e)
        self._synced_count = len(entries)

    def add(self, entry: dict):
        entries = self._load_all()
        if self._is_duplicate(entry.get("content", ""), entries):
            return
        entry["id"] = f"lesson_{len(entries) + 1:03d}"
        entry.setdefault("timestamp", "")
        entry.setdefault("tags", [])
        entry.setdefault("type", "lesson")
        entries.append(entry)
        if len(entries) > self.max_entries:
            entries = entries[-self.max_entries:]
        self.path.write_text(
            "\n".join(json.dumps(e) for e in entries),
            encoding="utf-8",
        )
        self.vector.add(entry)
        self._synced_count = len(entries)

    def clear(self):
        if self.path.exists():
            self.path.unlink()
        self.vector.clear()
        self._synced_count = 0

    def search(self, query: str, max_results: int = 3) -> list[dict]:
        return self.vector.search(query, max_results=max_results)

    def _load_all(self) -> list[dict]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").strip().split("\n") if line.strip()]

    def _is_duplicate(self, content: str, entries: list[dict]) -> bool:
        return any(e.get("content") == content for e in entries)
