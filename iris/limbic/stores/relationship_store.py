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

    @classmethod
    def make(
        cls,
        account_id: str,
        state: RelationshipState,
        room_id: str = "",
    ) -> RelationshipSnapshot:
        return cls(
            id=cls._compose_id(account_id, room_id),
            account_id=account_id,
            room_id=room_id,
            state=state,
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
    ) -> RelationshipSnapshot:
        snap = RelationshipSnapshot.make(account_id, state, room_id=room_id)
        existing = self.find(snap.id)
        if existing is not None:
            return self.update(snap.id, **snap.model_dump(mode="python"))  # type: ignore[return-value]
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
