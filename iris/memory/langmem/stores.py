"""MemoryExtractionJobStore / MemoryCandidateStore — ジョブと候補の JSONL 永続化。"""

from __future__ import annotations

from loguru import logger

from iris.memory.base import _IdIndexedJsonlStore
from iris.memory.langmem.dedup import compute_candidate_hash
from iris.memory.langmem.models import MemoryCandidate, MemoryExtractionJob


class MemoryExtractionJobStore(_IdIndexedJsonlStore[MemoryExtractionJob]):
    """LangMem 抽出ジョブの永続ストア。"""

    def __init__(self, path: str) -> None:
        super().__init__(path, MemoryExtractionJob)


class MemoryCandidateStore(_IdIndexedJsonlStore[MemoryCandidate]):
    """LangMem 出力を保持する候補ストア。PromotionPolicy の入力。

    ``payload_hash`` レベルでの重複検出を行い、pending 中の重複は追加しない。
    """

    def __init__(self, path: str, *, allow_duplicates: bool = False) -> None:
        super().__init__(path, MemoryCandidate)
        self._allow_duplicates = allow_duplicates

    def add(self, item: MemoryCandidate) -> MemoryCandidate:
        if not item.payload_hash:
            item.payload_hash = compute_candidate_hash(
                target_store=item.target_store,
                payload=item.payload,
                account_id=item.scope_account_id,
                room_id=item.scope_room_id,
            )
        if not self._allow_duplicates and self._has_pending_duplicate(item):
            logger.debug(
                "MemoryCandidateStore: skipping duplicate payload_hash={} target_store={}",
                item.payload_hash,
                item.target_store,
            )
            return item
        return super().add(item)

    def _has_pending_duplicate(self, item: MemoryCandidate) -> bool:
        if not item.payload_hash:
            return False
        for existing in self.list_filtered(
            target_store=item.target_store,
            scope_account_id=item.scope_account_id,
            scope_room_id=item.scope_room_id,
            payload_hash=item.payload_hash,
        ):
            if existing.status in ("pending", "promoted", "needs_review"):
                return True
        return False

    def find_by_payload_hash(
        self,
        target_store: str,
        payload_hash: str,
        *,
        account_id: str = "",
        room_id: str = "",
    ) -> MemoryCandidate | None:
        for existing in self.list_filtered(
            target_store=target_store,
            payload_hash=payload_hash,
            scope_account_id=account_id,
            scope_room_id=room_id,
        ):
            return existing
        return None


__all__ = ["MemoryCandidateStore", "MemoryExtractionJobStore"]
