from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from iris.event.base import Event


@dataclass
class RoomJoinedEvent(Event):
    room_id: str = ""
    account_id: str = ""
    display_name: str = ""


@dataclass
class RoomJoinedBatchEvent(Event):
    room_id: str = ""
    joins: list[RoomJoinedEvent] = field(default_factory=list)
    count: int = 0

    def to_dict(self) -> dict[str, Any]:
        result = super().to_dict()
        result["joins"] = [j.to_dict() for j in self.joins]
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Event:
        joins_raw = data.get("joins", [])
        data = {k: v for k, v in data.items() if k != "joins"}
        event = super().from_dict(data)
        if isinstance(event, RoomJoinedBatchEvent):
            event.joins = [RoomJoinedEvent.from_dict(j) if isinstance(j, dict) else j for j in joins_raw]  # type: ignore[misc]
        return event


@dataclass
class RoomLeftEvent(Event):
    room_id: str = ""
    account_id: str = ""
    display_name: str = ""


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
