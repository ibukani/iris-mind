from __future__ import annotations

import logging
import threading
from collections import defaultdict
from collections.abc import Callable
from contextlib import suppress
from datetime import UTC, datetime
from typing import Protocol, runtime_checkable

from iris.event.event_types import Event, new_trace_id


@runtime_checkable
class EventBusProtocol(Protocol):
    def publish(self, event: Event) -> None: ...

    def subscribe(self, event_type: str, handler: Callable) -> None: ...

    def unsubscribe(self, event_type: str, handler: Callable) -> None: ...


class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, list[Callable]] = defaultdict(list)
        self._lock: threading.Lock = threading.Lock()

    def publish(self, event: Event) -> None:
        if event.timestamp is None:
            event.timestamp = datetime.now(UTC)
        if not event.trace_id:
            event.trace_id = new_trace_id()
        event_type = type(event).__name__
        with self._lock:
            handlers = list(self._subscribers.get(event_type, []))
        for handler in handlers:
            try:
                handler(event)
            except Exception:
                logging.getLogger(__name__).exception(
                    "EventBus handler error in %s for %s",
                    handler.__qualname__,
                    event_type,
                )

    def subscribe(self, event_type: str, handler: Callable) -> None:
        with self._lock:
            self._subscribers[event_type].append(handler)

    def unsubscribe(self, event_type: str, handler: Callable) -> None:
        with self._lock, suppress(ValueError):
            self._subscribers[event_type].remove(handler)
