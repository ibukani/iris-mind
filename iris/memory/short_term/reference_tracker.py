from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from iris.memory.short_term.extractor import EntityExtractor
    from iris.memory.short_term.store import ShortTermStore


class ReferenceTracker:
    """entity / referenceの抽出・更新。"""

    def __init__(self, store: ShortTermStore, entity_extractor: EntityExtractor) -> None:
        self._store = store
        self._entity_extractor = entity_extractor

    def extract_references(self, content: str) -> None:
        for entity in self._entity_extractor.extract(content):
            self._store.add_reference(entity)
