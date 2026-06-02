"""Fake memory stores (episodic / semantic / vector / agents_md) と
それらを束ねる FakeMemoryManager。
"""

from __future__ import annotations

from dataclasses import dataclass, field


class FakeEpisodicStore:
    def __init__(self) -> None:
        self._entries: list[dict] = []

    def add(self, summary: str) -> None:
        self._entries.append({"summary": summary})

    def get_recent(self, n: int = 5) -> list[str]:
        return [e["summary"] for e in self._entries[-n:]]

    def clear(self) -> None:
        self._entries.clear()

    @property
    def count(self) -> int:
        return len(self._entries)


class FakeSemanticStore:
    def __init__(self) -> None:
        self._entries: list[dict] = []

    def add(self, entry: dict) -> None:
        if self._is_duplicate(entry.get("content", "")):
            return
        entry.setdefault("id", f"e{len(self._entries) + 1:03d}")
        entry.setdefault("tags", [])
        self._entries.append(entry)

    def search(self, query: str, max_results: int = 3) -> list[dict]:
        results = []
        for e in self._entries:
            if any(t in e.get("tags", []) for t in query.lower().split()):
                results.append({**e, "score": 0.8})
            elif query.lower() in e.get("content", "").lower():
                results.append({**e, "score": 0.6})
        return sorted(results, key=lambda x: x["score"], reverse=True)[:max_results]

    def clear(self) -> None:
        self._entries.clear()

    def _is_duplicate(self, content: str) -> bool:
        return any(e.get("content") == content for e in self._entries)

    @property
    def count(self) -> int:
        return len(self._entries)


class FakeVectorStore:
    def __init__(self) -> None:
        self._entries: list[dict] = []

    def add(self, entry: dict) -> None:
        self._entries.append(entry)

    def update(self, entry: dict) -> None:
        for i, e in enumerate(self._entries):
            if e.get("id") == entry.get("id"):
                self._entries[i] = entry
                return

    def delete(self, eid: str) -> None:
        self._entries = [e for e in self._entries if e.get("id") != eid]

    def clear(self) -> None:
        self._entries.clear()

    def search(self, query: str, max_results: int = 3, min_score: float = 0.0) -> list[dict]:
        results = []
        for e in self._entries:
            content = e.get("content", "")
            score = 0.7 + len(query) / max(len(content), 1) * 0.3 if query.lower() in content.lower() else 0.1
            if score >= min_score:
                results.append({**e, "score": min(score, 1.0)})
        return sorted(results, key=lambda x: x["score"], reverse=True)[:max_results]

    def count(self) -> int:
        return len(self._entries)


@dataclass
class FakeMemoryManager:
    episodic: FakeEpisodicStore = field(default_factory=FakeEpisodicStore)
    semantic: FakeSemanticStore = field(default_factory=FakeSemanticStore)
    vector_store: FakeVectorStore = field(default_factory=FakeVectorStore)
    _preferences: list[dict] = field(default_factory=list)

    def search_semantic(self, query: str, max_results: int = 3) -> list[dict]:
        return self.semantic.search(query, max_results=max_results)

    def get_user_preferences(self) -> list[dict]:
        return self._preferences

    def add_episodic(self, content: str, kind: str = "user_input", metadata: dict | None = None) -> None:
        self.episodic.add(content)

    def add_semantic(self, content: str, tags: list[str] | None = None) -> None:
        self.semantic.add({"content": content, "tags": tags or []})

    def add_semantic_by_type(self, entry_type: str, content: str, tags: list[str] | None = None) -> None:
        self.semantic.add({"content": content, "tags": tags or [], "type": entry_type})

    def get_recent(self, n: int = 3) -> list[dict]:
        entries = self.episodic.get_recent(n)
        return [{"summary": e} for e in entries]


class FakeAgentsMdStore:
    def __init__(self, content: str = "") -> None:
        self._content = content
        self.update_called_with: str | None = None

    def load(self) -> str:
        return self._content

    def update(self, new_content: str) -> None:
        self._content = new_content
        self.update_called_with = new_content


__all__ = [
    "FakeAgentsMdStore",
    "FakeEpisodicStore",
    "FakeMemoryManager",
    "FakeSemanticStore",
    "FakeVectorStore",
]
