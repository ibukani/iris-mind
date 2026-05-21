from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from contextlib import suppress
from datetime import UTC, datetime
import logging
import threading
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from iris.event.event_types import Event, new_trace_id

if TYPE_CHECKING:
    from iris.event.tracer import EventTracer


@runtime_checkable
class EventBusProtocol(Protocol):
    def publish(self, event: Event) -> None: ...

    def subscribe(self, event_type: str, handler: Callable) -> None: ...

    def unsubscribe(self, event_type: str, handler: Callable) -> None: ...


class EventBus:
    """グローバル イベントバス。全層間の疎結合通信を実現する。

    publisher は event を publish し、
    subscriber は event_type 別に handler を登録して受信する。
    スレッドセーフ。
    """

    def __init__(self, tracer: EventTracer | None = None) -> None:
        self._subscribers: dict[str, list[Callable]] = defaultdict(list)
        self._lock: threading.Lock = threading.Lock()
        self._tracer = tracer

    def set_tracer(self, tracer: EventTracer | None) -> None:
        self._tracer = tracer

    def publish(self, event: Event) -> None:
        """イベントを全購読者に配信する。

        Args:
            event: 発行するイベント。timestamp と trace_id は自動付与される。
        """
        if event.timestamp is None:
            event.timestamp = datetime.now(UTC)
        if not event.trace_id:
            event.trace_id = new_trace_id()
        if self._tracer is not None:
            self._tracer.on_event(event)
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
        """イベント型に対するハンドラを登録する。

        Args:
            event_type: 購読するイベント型の名前。
            handler: イベント発生時に呼び出される関数。
        """
        with self._lock:
            self._subscribers[event_type].append(handler)

    def unsubscribe(self, event_type: str, handler: Callable) -> None:
        """ハンドラの登録を解除する。

        Args:
            event_type: 対象のイベント型。
            handler: 登録解除するハンドラ関数。
        """
        with self._lock, suppress(ValueError):
            self._subscribers[event_type].remove(handler)
