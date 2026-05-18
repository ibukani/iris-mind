from __future__ import annotations

from datetime import UTC, datetime
import logging
from typing import Any

logger = logging.getLogger(__name__)


class ShortTermMemory:
    """短期記憶 / ワーキングメモリ。
    処理中の情報（直近の会話・思考）を一時的に保持し、
    重要度や回数に応じて長期記憶（エピソード記憶・意味記憶）へ転送する。
    """

    def __init__(self, max_entries: int = 10):
        self._entries: list[dict[str, Any]] = []
        self._max_entries = max_entries

    def add(self, content: str, metadata: dict[str, Any] | None = None) -> None:
        entry: dict[str, Any] = {
            "content": content,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        if metadata:
            entry["metadata"] = metadata
        self._entries.append(entry)
        if len(self._entries) > self._max_entries:
            self._entries.pop(0)
        logger.debug("ShortTermMemory: added entry, total=%d", len(self._entries))

    def get_recent(self, n: int = 5) -> list[dict[str, Any]]:
        return self._entries[-n:]

    def clear(self) -> None:
        self._entries.clear()
        logger.debug("ShortTermMemory: cleared")

    @property
    def entries(self) -> list[dict[str, Any]]:
        return list(self._entries)

    @property
    def count(self) -> int:
        return len(self._entries)

    @property
    def is_full(self) -> bool:
        return len(self._entries) >= self._max_entries
