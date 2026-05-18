from __future__ import annotations

from datetime import UTC, datetime
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

_MAX_TURN_LENGTH = 500
_MAX_CONTEXT_CHARS = 600


class ShortTermMemoryManager:
    def __init__(self, max_turns: int = 10, max_topics: int = 5):
        self._turns: list[dict[str, Any]] = []
        self._current_topics: list[str] = []
        self._active_references: set[str] = set()
        self._max_turns = max_turns
        self._max_topics = max_topics

    def add_turn(self, role: str, content: str) -> None:
        if not content:
            return
        truncated = content[:_MAX_TURN_LENGTH]
        entry: dict[str, Any] = {
            "role": role,
            "content": truncated,
            "timestamp": datetime.now(UTC).isoformat(),
            "consolidated": False,
            "importance": self._compute_importance(truncated),
        }
        self._turns.append(entry)
        if len(self._turns) > self._max_turns:
            self._turns.pop(0)
        self._extract_from_content(truncated)
        logger.debug("ShortTerm: added %s turn, total=%d", role, len(self._turns))

    def _compute_importance(self, content: str) -> int:
        score = 0
        lower = content.lower()
        if any(w in lower for w in ["important", "大事", "覚えて", "remember", "注意", "critical", "urgent"]):
            score += 3
        if any(w in lower for w in ["please", "お願い", "help", "assist", "question", "質問"]):
            score += 1
        if re.search(r"[A-Z]{3,}", content):
            score += 1
        if content.count("!") >= 2:
            score += 1
        return min(score, 5)

    def _extract_from_content(self, content: str) -> None:
        for entity in self._extract_entities(content):
            self._active_references.add(entity)
        sentences = re.split(r"[。！？\.\!\?]", content)
        for s in sentences[:2]:
            s = s.strip()
            if len(s) > 5 and len(s) < 80 and s not in self._current_topics:
                self._current_topics.append(s)
        if len(self._current_topics) > self._max_topics:
            self._current_topics = self._current_topics[-self._max_topics :]

    def _extract_entities(self, content: str) -> list[str]:
        entities: list[str] = []
        entities.extend(re.findall(r"https?://[^\s]+", content))
        entities.extend(re.findall(r"(?:/[^\s/]+)+(?:/?)", content))
        entities.extend(re.findall(r"#\w+", content))
        entities.extend(re.findall(r"@\w+", content))
        entities.extend(re.findall(r"「([^」]+)」", content))
        entities.extend(re.findall(r'"([^"]{3,})"', content))
        entities.extend(re.findall(r"\b[A-Z][a-z]+(?:[A-Z][a-z]+)*\b", content))
        return list({e for e in entities if len(e) > 2})

    def _compute_relevance(self, query: str, turn: dict[str, Any]) -> float:
        if not query or not turn.get("content"):
            return 0.0
        q_words = set(re.findall(r"\w+", query.lower()))
        t_words = set(re.findall(r"\w+", turn["content"].lower()))
        if not q_words or not t_words:
            return 0.0
        overlap = len(q_words & t_words)
        return overlap / len(q_words)

    def search(self, query: str, max_results: int = 5) -> list[dict[str, Any]]:
        scored: list[tuple[float, int, dict[str, Any]]] = []
        for i, turn in enumerate(self._turns):
            relevance = self._compute_relevance(query, turn)
            if relevance > 0 or (query and query.lower() in turn.get("content", "").lower()):
                if relevance == 0:
                    relevance = 0.01
                scored.append((relevance, turn.get("importance", 0), dict(turn)))
                scored[-1][2]["relevance"] = relevance
                scored[-1][2]["index"] = i
        scored.sort(key=lambda x: (-x[0], -x[1]))
        return [s[2] for s in scored[:max_results]]

    def search_entities(self, entity_name: str) -> list[dict[str, Any]]:
        entity_lower = entity_name.lower().strip()
        results: list[dict[str, Any]] = []
        for i, turn in enumerate(self._turns):
            if entity_lower in turn.get("content", "").lower():
                turn_copy = dict(turn)
                turn_copy["index"] = i
                results.append(turn_copy)
        return results[-5:]

    def render_context(self, max_chars: int = _MAX_CONTEXT_CHARS, query: str | None = None) -> str:
        if not self._turns:
            return ""
        parts: list[str] = []

        if query:
            parts.append("### 直近の会話（関連）")
            relevant = self.search(query, max_results=3)
            shown_indices: set[int] = set()
            for r in relevant:
                shown_indices.add(r.get("index", -1))
                label = "User" if r["role"] == "user" else "Iris"
                parts.append(f"- {label}: 「{r['content'][:100]}」(関連度 {r.get('relevance', 0):.2f})")
            for t in reversed(self._turns[-4:]):
                idx = self._turns.index(t)
                if idx in shown_indices:
                    continue
                shown_indices.add(idx)
                label = "User" if t["role"] == "user" else "Iris"
                parts.append(f"- {label}: 「{t['content'][:100]}」")

        if self._current_topics:
            parts.append("### 現在の話題")
            parts.extend(f"- {topic}" for topic in self._current_topics[-3:])
        if self._active_references:
            refs = sorted(self._active_references, key=len, reverse=True)[:5]
            parts.append("### 参照エンティティ")
            parts.append(", ".join(refs))

        if not parts:
            return ""
        text = "\n".join(parts)
        if len(text) > max_chars:
            text = text[: max_chars - 3] + "..."
        return text

    def get_recent_turns(self, n: int = 4) -> list[dict[str, Any]]:
        return self._turns[-n:]

    def get_unconsolidated_turns(self) -> list[dict[str, Any]]:
        return [t for t in self._turns if not t.get("consolidated")]

    def mark_consolidated(self, up_to_index: int | None = None) -> None:
        if up_to_index is None:
            for t in self._turns:
                t["consolidated"] = True
        else:
            for t in self._turns[:up_to_index]:
                t["consolidated"] = True

    def clear(self) -> None:
        self._turns.clear()
        self._current_topics.clear()
        self._active_references.clear()

    def should_consolidate(self) -> bool:
        return len(self._turns) >= self._max_turns

    @property
    def current_topics(self) -> list[str]:
        return list(self._current_topics)

    @property
    def turn_count(self) -> int:
        return len(self._turns)
