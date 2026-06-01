from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from iris.memory.models import ContentBlock, blocks_text
from iris.memory.short_term.models import (
    MAX_TURN_LENGTH,
    ShortTermScope,
    ShortTermSearchResult,
    ShortTermTurn,
)


def _truncate_blocks(blocks: list[ContentBlock], max_chars: int) -> list[ContentBlock]:
    total = 0
    result: list[ContentBlock] = []
    for b in blocks:
        txt = b.get("text", "")
        available = max_chars - total
        if available <= 0:
            break
        if not txt or len(txt) <= available:
            result.append(b)
            total += len(txt)
        else:
            tb: ContentBlock = {"type": b.get("type", "text")}
            tb["text"] = txt[:available]
            result.append(tb)
            total += available
    return result


class ShortTermStore:
    """turn / topic / reference の状態保持。"""

    def __init__(self, max_turns: int = 30, max_topics: int = 5) -> None:
        self._turns: list[ShortTermTurn] = []
        self._current_topics: list[str] = []
        self._active_references: set[str] = set()
        self._max_turns = max_turns
        self._max_topics = max_topics

    def append_turn(
        self,
        role: str,
        blocks: list[ContentBlock],
        text: str,
        importance: int,
        account_id: str = "",
        room_id: str = "",
    ) -> ShortTermTurn:
        truncated = _truncate_blocks(blocks, MAX_TURN_LENGTH)
        entry = ShortTermTurn(
            role=role,
            blocks=truncated,
            timestamp=datetime.now(UTC).isoformat(),
            consolidated=False,
            importance=importance,
            account_id=account_id,
            room_id=room_id,
        )
        self._turns.append(entry)
        if len(self._turns) > self._max_turns:
            self._turns.pop(0)
        return entry

    def _scope(self, scope: ShortTermScope) -> list[ShortTermTurn]:
        turns = self._turns
        if scope.account_id:
            turns = [t for t in turns if t.account_id == scope.account_id]
        if scope.room_id:
            turns = [t for t in turns if t.room_id == scope.room_id]
        return turns

    def scope_turns(self, room_id: str = "", account_id: str = "") -> list[ShortTermTurn]:
        return self._scope(ShortTermScope(room_id=room_id, account_id=account_id))

    def get_recent_turns(
        self,
        n: int = 4,
        room_id: str = "",
        account_id: str = "",
    ) -> list[ShortTermTurn]:
        return self._scope(ShortTermScope(room_id=room_id, account_id=account_id))[-n:]

    def get_unconsolidated_turns(
        self,
        room_id: str = "",
        account_id: str = "",
    ) -> list[ShortTermTurn]:
        return [t for t in self._scope(ShortTermScope(room_id=room_id, account_id=account_id)) if not t.consolidated]

    def mark_consolidated(self, room_id: str = "", account_id: str = "") -> None:
        """指定スコープ内の未consolidated turnをconsolidatedにする。"""
        for t in self._scope(ShortTermScope(room_id=room_id, account_id=account_id)):
            t.consolidated = True

    def turn_text(self, turn: ShortTermTurn) -> str:
        return blocks_text(turn.blocks)

    def add_topic(self, topic: str) -> None:
        if topic not in self._current_topics:
            self._current_topics.append(topic)
        if len(self._current_topics) > self._max_topics:
            self._current_topics = self._current_topics[-self._max_topics :]

    def add_reference(self, ref: str) -> None:
        self._active_references.add(ref)

    @property
    def turns(self) -> list[ShortTermTurn]:
        return self._turns

    @property
    def turn_count(self) -> int:
        return len(self._turns)

    @property
    def max_turns(self) -> int:
        return self._max_turns

    @property
    def current_topics(self) -> list[str]:
        return list(self._current_topics)

    @property
    def active_references(self) -> set[str]:
        return self._active_references

    def clear(self) -> None:
        self._turns.clear()
        self._current_topics.clear()
        self._active_references.clear()


__all__ = ["ShortTermScope", "ShortTermSearchResult", "ShortTermStore"]


def _legacy_to_dict(turn: ShortTermTurn) -> dict[str, Any]:
    return turn.to_dict()
