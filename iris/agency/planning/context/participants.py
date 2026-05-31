from __future__ import annotations

from iris.memory.manager import MemoryManager


class ParticipantsProvider:
    def __init__(self, memory: MemoryManager) -> None:
        self._memory = memory

    def build(self, room_id: str) -> str:
        if not room_id:
            return ""
        try:
            users = self._memory.short_term.get_users_by_room(room_id)
            if len(users) <= 1:
                return ""
            names = [nick for _, nick in users]
            return f"このルームの参加者: {', '.join(names)}"
        except Exception:
            return ""
