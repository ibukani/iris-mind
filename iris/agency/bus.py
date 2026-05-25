from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
import threading

from loguru import logger

from iris.agency.planning.models import Plan


@dataclass
class PlanDecided:
    plan: Plan


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
                logger.exception(
                    "InternalBus handler error in {} for {}",
                    handler.__qualname__,
                    event_type,
                )

    def subscribe(self, event_type: str, handler: Callable) -> None:
        with self._lock:
            self._subscribers[event_type].append(handler)

    def unsubscribe(self, event_type: str, handler: Callable) -> None:
        with self._lock, suppress(ValueError):
            self._subscribers[event_type].remove(handler)
