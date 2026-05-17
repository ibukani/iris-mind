from __future__ import annotations

import logging
import threading
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from contextlib import suppress


@dataclass
class PlanDecided:
    plan: dict


@dataclass
class ExecutionResult:
    session_id: str
    success: bool
    summary: str
    messages: list[dict]


@dataclass
class ExecutionFeedback:
    session_id: str
    query: str
    context: dict


class InternalBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, list[Callable]] = defaultdict(list)
        self._lock: threading.Lock = threading.Lock()

    def publish(self, event: object) -> None:
        event_type = type(event).__name__
        with self._lock:
            handlers = list(self._subscribers.get(event_type, []))
        for handler in handlers:
            try:
                handler(event)
            except Exception:
                logging.getLogger(__name__).exception(
                    "InternalBus handler error in %s for %s",
                    handler.__qualname__,
                    event_type,
                )

    def subscribe(self, event_type: str, handler: Callable) -> None:
        with self._lock:
            self._subscribers[event_type].append(handler)

    def unsubscribe(self, event_type: str, handler: Callable) -> None:
        with self._lock, suppress(ValueError):
            self._subscribers[event_type].remove(handler)
