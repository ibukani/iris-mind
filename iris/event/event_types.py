from __future__ import annotations

from dataclasses import dataclass, field
from dataclasses import fields as _fields
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any, ClassVar
import uuid as _uuid

if TYPE_CHECKING:
    pass


@dataclass(kw_only=True)
class Event:
    timestamp: datetime | None
    source: str
    trace_id: str = ""

    _type_registry: ClassVar[dict[str, type[Event]]] = {}

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        Event._type_registry[cls.__name__] = cls

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"type": type(self).__name__}
        for f in _fields(self):
            val = getattr(self, f.name)
            if isinstance(val, datetime):
                result[f.name] = val.isoformat()
            else:
                result[f.name] = val
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Event:
        event_cls = cls._resolve_type(data["type"])
        kwargs: dict[str, Any] = {}
        for f in _fields(event_cls):
            if f.name not in data:
                continue
            val = data[f.name]
            if isinstance(val, str) and f.name == "timestamp":
                kwargs[f.name] = datetime.fromisoformat(val) if val else None
            else:
                kwargs[f.name] = val
        return event_cls(**kwargs)

    @classmethod
    def _resolve_type(cls, name: str) -> type[Event]:
        if name in cls._type_registry:
            return cls._type_registry[name]
        raise ValueError(f"Unknown event type: {name}")


@dataclass
class TimerTick(Event):
    tick_count: int = 0


@dataclass
class AgentStateChangeEvent(Event):
    previous_state: str | None
    new_state: str | None


@dataclass
class MemoryUpdateEvent(Event):
    entry_type: str
    content: str


@dataclass
class AgentAnomalyEvent(Event):
    anomaly_type: str
    severity: str
    detail: str


@dataclass
class Identity:
    """発話者識別情報。"""

    provider: str = ""
    subject: str = ""
    provider_name: str = ""
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass
class MessageEvent(Event):
    session_id: str = ""
    source_role: str = ""
    target_role: str = ""
    account_id: str = ""
    direction: str = ""
    msg_type: str = ""
    content: str = ""
    state: str | None = None
    correlation_id: str | None = None
    room_id: str = ""
    speaker: Identity | None = None


@dataclass
class InputReady(Event):
    timestamp: datetime | None = None
    source: str = ""
    session_id: str = ""
    content: str = ""
    account_id: str = ""
    room_id: str = ""
    context: dict | None = None


@dataclass
class DebugSnapshotEvent(Event):
    category: str = ""
    data: dict | None = None
    trigger: str = ""


@dataclass
class InterruptEvent(Event):
    room_id: str = ""


class InhibitionAction(StrEnum):
    SUPPRESS = "suppress"
    UNSUPPRESS = "unsuppress"
    HYPERDIRECT = "hyperdirect"


@dataclass
class InhibitionEvent(Event):
    action: InhibitionAction = InhibitionAction.SUPPRESS
    reason: str = ""
    duration: float = 0.0
    room_id: str = ""


@dataclass
class SessionDisconnectEvent(Event):
    session_id: str = ""
    session_tag: str = ""


@dataclass
class ControlMessageEvent(Event):
    action: str = ""
    account_id: str = ""
    room_id: str = ""
    display_name: str = ""
    text: str = ""
    session_id: str = ""
    identity: dict[str, Any] | None = None
    profile: dict[str, str] | None = None
    metadata: dict[str, str] | None = None


@dataclass
class RoomJoinedEvent(Event):
    room_id: str = ""
    account_id: str = ""
    display_name: str = ""


@dataclass
class RoomLeftEvent(Event):
    room_id: str = ""
    account_id: str = ""
    display_name: str = ""


def new_trace_id() -> str:
    return _uuid.uuid4().hex[:12]


__all__ = [
    "AgentAnomalyEvent",
    "AgentStateChangeEvent",
    "ControlMessageEvent",
    "DebugSnapshotEvent",
    "Event",
    "Identity",
    "InhibitionAction",
    "InhibitionEvent",
    "InputReady",
    "InterruptEvent",
    "MemoryUpdateEvent",
    "MessageEvent",
    "RoomJoinedEvent",
    "RoomLeftEvent",
    "SessionDisconnectEvent",
    "TimerTick",
    "new_trace_id",
]
