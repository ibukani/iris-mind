from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RoomState(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


RoomMetadata = dict[str, object]


class Room(BaseModel):
    """ルーム情報。"""

    room_id: str = ""
    name: str = ""
    description: str = ""
    topic: str = ""
    state: RoomState = RoomState.ACTIVE
    created_by: str = ""
    created_at: str = ""
    updated_at: str | None = None
    metadata: RoomMetadata = Field(default_factory=dict)

    @model_validator(mode="after")
    def set_defaults(self) -> Room:
        if not self.room_id:
            self.room_id = uuid4().hex[:16]
        if not self.created_at:
            self.created_at = datetime.now(UTC).isoformat()
        return self


class RoomMember(BaseModel):
    """ルームメンバー情報。"""

    room_id: str
    account_id: str
    session_ids: list[str] = Field(default_factory=list)
    role: str = "member"
    joined_at: str = ""
    last_active: str | None = None
    disconnected_at: str | None = None

    @model_validator(mode="before")
    @classmethod
    def convert_session_id(cls, data: Any) -> Any:
        if isinstance(data, dict) and "session_ids" not in data and "session_id" in data:
            val = data["session_id"]
            data["session_ids"] = [str(val)] if val else []
        return data

    @model_validator(mode="after")
    def set_defaults(self) -> RoomMember:
        if not self.joined_at:
            self.joined_at = datetime.now(UTC).isoformat()
        return self

    @property
    def is_active(self) -> bool:
        return self.disconnected_at is None


class RoomUpdate(BaseModel):
    """ルーム更新要求。"""

    model_config = ConfigDict(frozen=True)

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
