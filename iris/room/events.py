from __future__ import annotations

from typing import Any

from pydantic import Field

from iris.event.base import Event


class RoomJoinedEvent(Event):
    room_id: str = ""
    account_id: str = ""
    display_name: str = ""


class RoomJoinedBatchEvent(Event):
    room_id: str = ""
    joins: list[RoomJoinedEvent] = Field(default_factory=list)
    count: int = 0


class RoomLeftEvent(Event):
    room_id: str = ""
    account_id: str = ""
    display_name: str = ""


class RoomCreatedEvent(Event):
    room_id: str = ""
    name: str = ""
    created_by: str = ""


class RoomDeletedEvent(Event):
    room_id: str = ""


class RoomUpdatedEvent(Event):
    room_id: str = ""
    field_name: str = ""
    old_value: Any = None
    new_value: Any = None
