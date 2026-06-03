from __future__ import annotations

from iris.agency.planning.context.time_format import format_age
from iris.memory.manager import MemoryManager


class SemanticProvider:
    def __init__(self, memory: MemoryManager) -> None:
        self._memory = memory

    def build(self, content: str, room_id: str = "") -> str | None:
        results = self._memory.search_semantic(content, max_results=2, room_id=room_id)
        if not results:
            return None
        best = max(results, key=lambda r: r.get("score", 0))
        if best.get("score", 0) <= 0.5:
            return None
        ts = format_age(best.get("timestamp", ""))
        label = f"関連記憶: {best.get('content', '')[:60]}"
        if ts:
            label += f"（{ts}）"
        return label
