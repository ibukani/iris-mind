from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import cast
from uuid import uuid4


class RoomState(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


@dataclass
class Room:
    """ルーム情報。"""

    room_id: str = ""
    name: str = ""
    description: str = ""
    topic: str = ""
    state: RoomState = RoomState.ACTIVE
    created_by: str = ""
    created_at: str = ""
    updated_at: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.room_id:
            self.room_id = uuid4().hex[:16]
        if not self.created_at:
            self.created_at = datetime.now(UTC).isoformat()

    def to_dict(self) -> dict[str, object]:
        return {
            "room_id": self.room_id,
            "name": self.name,
            "description": self.description,
            "topic": self.topic,
            "state": self.state.value,
            "created_by": self.created_by,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> Room:
        updated_at: str | None = None
        if isinstance(data.get("updated_at"), str):
            updated_at = cast(str, data["updated_at"])
        raw_metadata = data.get("metadata", {})
        metadata: dict[str, object] = {}
        if isinstance(raw_metadata, dict):
            metadata = cast("dict[str, object]", raw_metadata)
        state_str = str(data.get("state", RoomState.ACTIVE.value))
        try:
            state = RoomState(state_str)
        except ValueError:
            state = RoomState.ACTIVE
        return cls(
            room_id=str(data.get("room_id", "")),
            name=str(data.get("name", "")),
            description=str(data.get("description", "")),
            topic=str(data.get("topic", "")),
            state=state,
            created_by=str(data.get("created_by", "")),
            created_at=str(data.get("created_at", "")),
            updated_at=updated_at,
            metadata=metadata,
        )


@dataclass
class RoomMember:
    """ルームメンバー情報。"""

    room_id: str
    account_id: str
    session_id: str = ""
    role: str = "member"
    joined_at: str = ""
    last_active: str | None = None
    disconnected_at: str | None = None

    def __post_init__(self) -> None:
        if not self.joined_at:
            self.joined_at = datetime.now(UTC).isoformat()

    @property
    def is_active(self) -> bool:
        return self.disconnected_at is None

    def to_dict(self) -> dict[str, object]:
        return {
            "room_id": self.room_id,
            "account_id": self.account_id,
            "session_id": self.session_id,
            "role": self.role,
            "joined_at": self.joined_at,
            "last_active": self.last_active,
            "disconnected_at": self.disconnected_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> RoomMember:
        last_active: str | None = None
        if isinstance(data.get("last_active"), str):
            last_active = cast(str, data["last_active"])
        disconnected_at: str | None = None
        if isinstance(data.get("disconnected_at"), str):
            disconnected_at = cast(str, data["disconnected_at"])
        return cls(
            room_id=str(data.get("room_id", "")),
            account_id=str(data.get("account_id", "")),
            session_id=str(data.get("session_id", "")),
            role=str(data.get("role", "member")),
            joined_at=str(data.get("joined_at", "")),
            last_active=last_active,
            disconnected_at=disconnected_at,
        )
