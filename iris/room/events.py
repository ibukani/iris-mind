from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from iris.event.event_types import Event, RoomJoinedEvent, RoomLeftEvent  # noqa: F401


@dataclass
class RoomCreatedEvent(Event):
    room_id: str = ""
    name: str = ""
    created_by: str = ""


@dataclass
class RoomDeletedEvent(Event):
    room_id: str = ""


@dataclass
class RoomUpdatedEvent(Event):
    room_id: str = ""
    field_name: str = ""
    old_value: Any = None
    new_value: Any = None
