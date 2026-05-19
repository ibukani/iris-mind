from __future__ import annotations

from dataclasses import dataclass
from dataclasses import fields as _fields
from datetime import datetime
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
class MessageEvent(Event):
    session_id: str = ""
    source_role: str = ""
    target_role: str = ""
    direction: str = ""
    msg_type: str = ""
    content: str = ""
    state: str | None = None
    correlation_id: str | None = None


@dataclass
class InputReady(Event):
    session_id: str = ""
    content: str = ""
    context: dict | None = None


def new_trace_id() -> str:
    return _uuid.uuid4().hex[:12]


__all__ = [
    "AgentAnomalyEvent",
    "AgentStateChangeEvent",
    "Event",
    "InputReady",
    "MemoryUpdateEvent",
    "MessageEvent",
    "TimerTick",
    "new_trace_id",
]
