from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4


class RoomState(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


RoomMetadata = dict[str, object]


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
    metadata: RoomMetadata = field(default_factory=dict)

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
        updated_at_raw = data.get("updated_at")
        updated_at = updated_at_raw if isinstance(updated_at_raw, str) else None
        raw_metadata = data.get("metadata", {})
        metadata: RoomMetadata = dict(raw_metadata) if isinstance(raw_metadata, dict) else {}
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
    session_ids: list[str] = field(default_factory=list)
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
            "session_ids": self.session_ids,
            "role": self.role,
            "joined_at": self.joined_at,
            "last_active": self.last_active,
            "disconnected_at": self.disconnected_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> RoomMember:
        last_active_val = data.get("last_active")
        last_active = last_active_val if isinstance(last_active_val, str) else None
        disconnected_at_val = data.get("disconnected_at")
        disconnected_at = disconnected_at_val if isinstance(disconnected_at_val, str) else None
        raw_session_ids = data.get("session_ids", [])
        session_ids: list[str] = (
            [str(s) for s in raw_session_ids]
            if isinstance(raw_session_ids, list)
            else (
                [str(data["session_id"])] if isinstance(data.get("session_id"), str) and data.get("session_id") else []
            )
        )
        return cls(
            room_id=str(data.get("room_id", "")),
            account_id=str(data.get("account_id", "")),
            session_ids=session_ids,
            role=str(data.get("role", "member")),
            joined_at=str(data.get("joined_at", "")),
            last_active=last_active,
            disconnected_at=disconnected_at,
        )


@dataclass(frozen=True, slots=True)
class RoomUpdate:
    """ルーム更新要求。"""

    name: str | None = None
    description: str | None = None
    topic: str | None = None
    state: RoomState | None = None
    metadata: RoomMetadata | None = None

    def to_field_kwargs(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        if self.name is not None:
            result["name"] = self.name
        if self.description is not None:
            result["description"] = self.description
        if self.topic is not None:
            result["topic"] = self.topic
        if self.state is not None:
            result["state"] = self.state
        if self.metadata is not None:
            result["metadata"] = self.metadata
        return result


__all__ = [
    "Room",
    "RoomMember",
    "RoomMetadata",
    "RoomState",
    "RoomUpdate",
]
