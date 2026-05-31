from __future__ import annotations

from iris.agency.planning.context.randomizer import SeedableRandom
from iris.memory.manager import MemoryManager


class RandomMemoryProvider:
    def __init__(self, memory: MemoryManager, rng: SeedableRandom | None = None) -> None:
        self._memory = memory
        self._rng = rng or SeedableRandom.default()

    def build(self) -> str | None:
        try:
            recent = self._memory.get_recent(10)
            if not recent:
                return None
            entry = self._rng.choice(recent)
            summary = entry.get("summary", "") or entry.get("content", "")
            if not summary:
                return None
            return f"ふと思い出したこと: {summary[:60]}"
        except Exception:
            return None
