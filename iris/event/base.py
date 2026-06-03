from __future__ import annotations

import builtins
from datetime import datetime
from typing import Any, ClassVar
import uuid as _uuid

from pydantic import BaseModel, ConfigDict


class Event(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    timestamp: datetime | None = None
    source: str
    trace_id: str = ""
    type: str = ""

    _type_registry: ClassVar[dict[str, builtins.type[Event]]] = {}

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if cls.__name__ != "Event":
            Event._type_registry[cls.__name__] = cls

    def model_post_init(self, __context: Any) -> None:
        if not self.type:
            self.type = self.__class__.__name__

    @classmethod
    def model_validate(cls, obj: Any, *args: Any, **kwargs: Any) -> Any:
        if cls is Event and isinstance(obj, dict) and "type" in obj:
            type_name = obj["type"]
            if type_name in cls._type_registry:
                return cls._type_registry[type_name].model_validate(obj, *args, **kwargs)
            raise ValueError(f"Unknown event type: {type_name}")
        return super().model_validate(obj, *args, **kwargs)


class TimerTick(Event):
    tick_count: int = 0


class AgentStateChangeEvent(Event):
    previous_state: str | None = None
    new_state: str | None = None


class MemoryUpdateEvent(Event):
    entry_type: str
    content: str


class AgentAnomalyEvent(Event):
    anomaly_type: str
    severity: str
    detail: str


class DebugSnapshotEvent(Event):
    category: str = ""
    data: dict | None = None
    trigger: str = ""


def new_trace_id() -> str:
    return _uuid.uuid4().hex[:12]
