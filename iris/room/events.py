from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from iris.event.event_types import Event


@dataclass
class RoomCreatedEvent(Event):
    room_id: str = ""
    name: str = ""
    created_by: str = ""


@dataclass
class RoomDeletedEvent(Event):
    room_id: str = ""


@dataclass
class RoomJoinedEvent(Event):
    room_id: str = ""
    account_id: str = ""
    session_id: str = ""
    nickname: str = ""


@dataclass
class RoomLeftEvent(Event):
    room_id: str = ""
    account_id: str = ""
    session_id: str = ""
    nickname: str = ""


@dataclass
class RoomUpdatedEvent(Event):
    room_id: str = ""
    field_name: str = ""
    old_value: Any = None
    new_value: Any = None
