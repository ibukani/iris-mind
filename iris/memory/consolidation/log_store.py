"""Memory Consolidation Log Store — 昇格/却下イベントの永続化。"""

from __future__ import annotations

from iris.memory.consolidation.models import MemoryConsolidationRecord
from iris.memory.langmem.stores import _IdIndexedJsonlStore


class MemoryConsolidationLogStore(_IdIndexedJsonlStore[MemoryConsolidationRecord]):
    def __init__(self, path: str) -> None:
        super().__init__(path, MemoryConsolidationRecord)


__all__ = ["MemoryConsolidationLogStore"]
