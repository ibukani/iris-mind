"""RelationshipStateStore — 関係性スナップショットを JSONL に永続化する。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
import uuid

from pydantic import BaseModel, Field

from iris.limbic.models import RelationshipState
from iris.memory.langmem.stores import _IdIndexedJsonlStore


class RelationshipSnapshot(BaseModel):
    """永続化用の RelationshipState 拡張。"""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    account_id: str = ""
    room_id: str = ""
    state: RelationshipState = Field(default_factory=RelationshipState)
    updated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    # 直近更新を引き起こした MemoryCandidate の source_record_ids (LangMem 由来なら必須)
    source_record_ids: list[str] = Field(default_factory=list)
    # source_record_ids 累計 (重複除去済み)
    all_source_record_ids: list[str] = Field(default_factory=list)

    @classmethod
    def make(
        cls,
        account_id: str,
        state: RelationshipState,
        room_id: str = "",
        source_record_ids: list[str] | None = None,
    ) -> RelationshipSnapshot:
        return cls(
            id=cls._compose_id(account_id, room_id),
            account_id=account_id,
            room_id=room_id,
            state=state,
            source_record_ids=list(source_record_ids or []),
        )

    @staticmethod
    def _compose_id(account_id: str, room_id: str) -> str:
        return f"{account_id}::{room_id}" if room_id else f"{account_id}::__global__"


class RelationshipStateStore(_IdIndexedJsonlStore[RelationshipSnapshot]):
    """``account_id`` をキーにした RelationshipState スナップショット。"""

    def __init__(self, path: str) -> None:
        super().__init__(path, RelationshipSnapshot)

    def save_snapshot(
        self,
        account_id: str,
        state: RelationshipState,
        room_id: str = "",
        source_record_ids: list[str] | None = None,
    ) -> RelationshipSnapshot:
        snap = RelationshipSnapshot.make(
            account_id,
            state,
            room_id=room_id,
            source_record_ids=source_record_ids,
        )
        existing = self.find(snap.id)
        if existing is not None:
            merged = list(dict.fromkeys([*existing.all_source_record_ids, *snap.source_record_ids]))
            # orjson が RelationshipState (Pydantic) を直接シリアライズできないので
            # ``state`` を dict にしてから ``update`` に渡す。元の実装と同じ流儀。
            changes: dict[str, Any] = snap.model_dump(mode="python")
            changes["all_source_record_ids"] = merged
            return self.update(snap.id, **changes)  # type: ignore[return-value]
        if snap.source_record_ids:
            snap = snap.model_copy(update={"all_source_record_ids": list(snap.source_record_ids)})
        return self.add(snap)

    def load_for_account(self, account_id: str) -> RelationshipSnapshot | None:
        target = f"{account_id}::__global__"
        for s in self.list_all():
            if s.id == target:
                return s
        for s in self.list_all():
            if s.account_id == account_id:
                return s
        return None

    def list_for_account(self, account_id: str) -> list[RelationshipSnapshot]:
        return [s for s in self.list_all() if s.account_id == account_id]


__all__ = ["RelationshipSnapshot", "RelationshipStateStore"]


# silence unused import warning
_ = Any
