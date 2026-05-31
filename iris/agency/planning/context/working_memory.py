from __future__ import annotations

from loguru import logger

from iris.agency.planning.context.time_format import format_age
from iris.memory.manager import MemoryManager


class WorkingMemoryProvider:
    def __init__(self, memory: MemoryManager) -> None:
        self._memory = memory

    def build(self, query: str | None = None, room_id: str = "") -> str:
        try:
            wm = self._memory.short_term.render_context(query=query, room_id=room_id)
            if wm:
                return str(wm)

            recent = self._memory.get_recent(3, room_id=room_id)
            topics = [
                f"{e['summary'][:60]}（{format_age(e.get('timestamp', ''))}）"
                for e in recent
                if e.get("summary")
            ]
            if topics:
                return "直近の話題: " + " | ".join(topics)
        except Exception:
            logger.debug("Working context failed", exc_info=True)
        return ""
