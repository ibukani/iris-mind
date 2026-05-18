from __future__ import annotations

from datetime import UTC, datetime
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


class ShortTermMemoryManager:
    """短期記憶 / ワーキングメモリ。
    現在処理中の会話内容（ターン・話題・参照エンティティ）を保持し、
    長期記憶への転送（consolidation）を担う。

    書き込みタイミング:
    - add_turn("user", content): LLM応答生成直前 (ExecutionManager)
    - add_turn("assistant", content): LLM応答生成直後 (ExecutionManager)
    """

    def __init__(self, max_turns: int = 10, max_topics: int = 5):
        self._turns: list[dict[str, Any]] = []
        self._current_topics: list[str] = []
        self._active_references: set[str] = set()
        self._max_turns = max_turns
        self._max_topics = max_topics

    def add_turn(self, role: str, content: str) -> None:
        if not content:
            return
        entry: dict[str, Any] = {
            "role": role,
            "content": content,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        self._turns.append(entry)
        if len(self._turns) > self._max_turns:
            self._turns.pop(0)
        self._extract_from_content(content)
        logger.debug("ShortTerm: added %s turn, total=%d", role, len(self._turns))

    def _extract_from_content(self, content: str) -> None:
        words = re.findall(r"[A-Z][a-z]+(?:[A-Z][a-z]+)*", content)
        for w in words:
            if len(w) > 2:
                self._active_references.add(w)
        sentences = re.split(r"[。！？\.\!\?]", content)
        for s in sentences[:2]:
            s = s.strip()
            if len(s) > 5 and len(s) < 80 and s not in self._current_topics:
                self._current_topics.append(s)
        if len(self._current_topics) > self._max_topics:
            self._current_topics = self._current_topics[-self._max_topics :]

    def render_context(self) -> str:
        if not self._turns:
            return ""
        parts: list[str] = []
        parts.append("### 直近の会話")
        for t in self._turns[-4:]:
            label = "User" if t["role"] == "user" else "Iris"
            content = t["content"][:100]
            parts.append(f"- {label}: 「{content}」")
        if self._current_topics:
            parts.append("### 現在の話題")
            parts.extend(f"- {topic}" for topic in self._current_topics[-3:])
        if self._active_references:
            refs = list(self._active_references)[-5:]
            parts.append("### 参照エンティティ")
            parts.append(", ".join(refs))
        return "\n".join(parts)

    def get_recent_turns(self, n: int = 4) -> list[dict[str, Any]]:
        return self._turns[-n:]

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
