from __future__ import annotations

from loguru import logger

from iris.memory.manager import MemoryManager


class UserPreferencesProvider:
    def __init__(self, memory: MemoryManager) -> None:
        self._memory = memory

    def build(self, room_id: str = "", account_id: str = "") -> str | None:
        try:
            prefs = self._memory.get_user_preferences(room_id=room_id, account_id=account_id)
            if prefs:
                return f"ユーザーの関心: {prefs[0].get('content', '')[:80]}"
        except Exception:
            logger.debug("Memory hint failed", exc_info=True)
        return None
