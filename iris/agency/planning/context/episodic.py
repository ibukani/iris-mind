from __future__ import annotations

from iris.agency.planning.context.time_format import format_age
from iris.memory.manager import MemoryManager


class EpisodicProvider:
    def __init__(self, memory: MemoryManager) -> None:
        self._memory = memory

    def build(self, room_id: str = "") -> str | None:
        recent = self._memory.get_recent(3, room_id=room_id)
        for e in reversed(recent):
            s = e.get("summary", "")
            if not s:
                continue
            ts = format_age(e.get("timestamp", ""))
            if ts:
                label = "直前の話題" if ts == "たった今" else "過去の話題"
                return f"{label}: {s[:60]}（{ts}）"
            return f"話題: {s[:60]}"
        return None
