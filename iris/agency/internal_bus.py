from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
import threading
from typing import TYPE_CHECKING, TypeVar, overload

from loguru import logger

if TYPE_CHECKING:
    from iris.agency.planning.models import Plan

T = TypeVar("T")


@dataclass
class PlanDecided:
    plan: Plan


class InternalBus:
    """Agency層内部のイベントバス。Planning ↔ Execution 間の通信に使用。"""

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

    @overload
    def subscribe(self, event_type: type[T], handler: Callable[[T], None]) -> None: ...
    @overload
    def subscribe(self, event_type: str, handler: Callable[[object], None]) -> None: ...
    def subscribe(self, event_type: type[object] | str, handler: Callable[[object], None]) -> None:  # type: ignore[misc]
        key = event_type.__name__ if isinstance(event_type, type) else event_type
        with self._lock:
            self._subscribers[key].append(handler)

    @overload
    def unsubscribe(self, event_type: type[T], handler: Callable[[T], None]) -> None: ...
    @overload
    def unsubscribe(self, event_type: str, handler: Callable[[object], None]) -> None: ...
    def unsubscribe(self, event_type: type[object] | str, handler: Callable[[object], None]) -> None:  # type: ignore[misc]
        key = event_type.__name__ if isinstance(event_type, type) else event_type
        with self._lock, suppress(ValueError):
            self._subscribers[key].remove(handler)
