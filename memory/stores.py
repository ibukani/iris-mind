from __future__ import annotations
from pathlib import Path
import json


class AgentsMdStore:
    """構造記憶。AGENTS.mdの読み書き。サイズ上限を超えないよう制御。"""

    def __init__(self, path: str = "AGENTS.md", max_bytes: int = 2048):
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
        while len(content.encode("utf-8")) > self.max_bytes:
            lines = content.split("\n")
            content = "\n".join(lines[:-2])
        return content


class EpisodicStore:
    """エピソード記憶。日次サマリーを管理。"""

    def __init__(self, path: str = "memory/episodes.jsonl", max_entries: int = 30):
        self.path = Path(path)
        self.max_entries = max_entries

    def add(self, summary: str):
        entries = self._load_all()
        entries.append(summary)
        if len(entries) > self.max_entries:
            entries = entries[-self.max_entries:]
        self.path.write_text(
            "\n".join(json.dumps({"summary": e}) for e in entries),
            encoding="utf-8",
        )

    def get_recent(self, n: int = 5) -> list[str]:
        entries = self._load_all()
        return [e["summary"] for e in entries[-n:]]

    def _load_all(self) -> list[dict]:
        if not self.path.exists():
            return []
        return [
            json.loads(line)
            for line in self.path.read_text(encoding="utf-8").strip().split("\n")
            if line.strip()
        ]


class SemanticStore:
    """意味記憶。教訓・好みを管理（ベクトルDBはPhase 3）。"""

    def __init__(self, path: str = "memory/semantic.jsonl", max_entries: int = 100):
        self.path = Path(path)
        self.max_entries = max_entries

    def add(self, entry: dict):
        entries = self._load_all()
        if self._is_duplicate(entry.get("content", ""), entries):
            return
        entry["id"] = f"lesson_{len(entries) + 1:03d}"
        entries.append(entry)
        if len(entries) > self.max_entries:
            entries = entries[-self.max_entries:]
        self.path.write_text(
            "\n".join(json.dumps(e) for e in entries),
            encoding="utf-8",
        )

    def search(self, query: str, max_results: int = 3) -> list[dict]:
        entries = self._load_all()
        if not entries:
            return []
        query_lower = query.lower()
        scored = []
        for e in entries:
            content_lower = e.get("content", "").lower()
            tag_match = any(t.lower() in query_lower for t in e.get("tags", []))
            word_match = any(w in content_lower for w in query_lower.split())
            score = (2 if tag_match else 0) + (1 if word_match else 0)
            if score > 0:
                scored.append((score, e))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [e for _, e in scored[:max_results]]

    def _load_all(self) -> list[dict]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").strip().split("\n") if line.strip()]

    def _is_duplicate(self, content: str, entries: list[dict]) -> bool:
        return any(e.get("content") == content for e in entries)
