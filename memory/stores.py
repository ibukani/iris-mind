from __future__ import annotations
from pathlib import Path
import json

from memory.vector_store import VectorStore


class AgentsMdStore:
    """構造記憶。memory/iris_profile.mdの読み書き。サイズ上限を超えないよう制御。"""

    def __init__(self, path: str = "memory/iris_profile.md", max_bytes: int = 2048):
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
        sizes = [len(l.encode("utf-8")) + 1 for l in lines]
        total = sum(sizes)
        keep_from = 0
        while keep_from < len(lines) and total > self.max_bytes:
            total -= sizes[keep_from]
            keep_from += 1
        return "\n".join(lines[keep_from:])


class EpisodicStore:
    """エピソード記憶。日次サマリーを管理。上限到達時は古いものをマージして圧縮。"""

    def __init__(self, path: str = "memory/episodes.jsonl", max_entries: int = 30):
        self.path = Path(path)
        self.max_entries = max_entries

    def add(self, summary: str):
        entries = self._load_all()
        entries.append({"summary": summary})
        if len(entries) > self.max_entries:
            entries = self._compress(entries)
        self.path.write_text(
            "\n".join(json.dumps(e) for e in entries),
            encoding="utf-8",
        )

    def get_recent(self, n: int = 5) -> list[str]:
        entries = self._load_all()
        return [e["summary"] for e in entries[-n:]]

    def _compress(self, entries: list[dict]) -> list[dict]:
        """古いエントリを1つにマージ"""
        keep = self.max_entries - 1
        merged_text = " | ".join(e["summary"] for e in entries[:len(entries) - keep])
        return [{"summary": merged_text[:500]}] + entries[-(keep):]

    def _load_all(self) -> list[dict]:
        if not self.path.exists():
            return []
        return [
            json.loads(line)
            for line in self.path.read_text(encoding="utf-8").strip().split("\n")
            if line.strip()
        ]


class SemanticStore:
    """意味記憶。JSONL永続化 + VectorStore（ChromaDB + BM25）によるハイブリッド検索。"""

    def __init__(self, path: str = "memory/semantic.jsonl", max_entries: int = 100,
                 vector_db_path: str = "memory/chroma_db"):
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

    def search(self, query: str, max_results: int = 3) -> list[dict]:
        return self.vector.search(query, max_results=max_results)

    def _load_all(self) -> list[dict]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").strip().split("\n") if line.strip()]

    def _is_duplicate(self, content: str, entries: list[dict]) -> bool:
        return any(e.get("content") == content for e in entries)
