from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import UTC, datetime
import threading
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from loguru import logger

from iris.event.base import Event, new_trace_id

if TYPE_CHECKING:
    from iris.event.tracer import EventTracer


@dataclass
class EventBusMetrics:
    """EventBus の可観測性メトリクス。"""

    published: int = 0
    handled: int = 0
    errors: int = 0
    handler_times: dict[str, float] = field(default_factory=dict)

    def reset(self) -> None:
        self.published = 0
        self.handled = 0
        self.errors = 0
        self.handler_times.clear()

    def summary(self) -> dict[str, object]:
        return {
            "published": self.published,
            "handled": self.handled,
            "errors": self.errors,
            "handler_count": len(self.handler_times),
            "slowest_handlers": sorted(self.handler_times.items(), key=lambda x: x[1], reverse=True)[:5],
        }


@runtime_checkable
class EventBusProtocol(Protocol):
    def publish(self, event: Event, *, strict: bool = False) -> None: ...

    def subscribe[E: Event](self, event_type: type[E], handler: Callable[[E], None]) -> None: ...

    def unsubscribe[E: Event](self, event_type: type[E], handler: Callable[[E], None]) -> None: ...


class EventBus:
    """グローバル イベントバス。全層間の疎結合通信を実現する。

    publisher は event を publish し、
    subscriber は event_type 別に handler を登録して受信する。
    スレッドセーフ。

    型安全な登録:
        bus.subscribe(TimerTick, my_handler)  # 型推論が効く

    strict モード:
        bus.publish(event, strict=True)  # ハンドラ例外を再 raise
    """

    def __init__(self, tracer: EventTracer | None = None) -> None:
        self._subscribers: dict[str, list[Callable]] = defaultdict(list)
        self._lock: threading.Lock = threading.Lock()
        self._metrics_lock: threading.Lock = threading.Lock()
        self._tracer = tracer
        self._metrics = EventBusMetrics()

    def set_tracer(self, tracer: EventTracer | None) -> None:
        self._tracer = tracer

    @property
    def metrics(self) -> EventBusMetrics:
        return self._metrics

    def publish(self, event: Event, *, strict: bool = False) -> None:
        """イベントを全購読者に配信する。

        Args:
            event: 発行するイベント。timestamp と trace_id は自動付与される。
            strict: True の場合、ハンドラ例外を再 raise する（デバッグ用）。
        """
        if event.timestamp is None:
            event.timestamp = datetime.now(UTC)
        if not event.trace_id:
            event.trace_id = new_trace_id()
        if self._tracer is not None:
            self._tracer.on_event(event)
        event_type = type(event).__name__
        with self._metrics_lock:
            self._metrics.published += 1
        with self._lock:
            handlers = list(self._subscribers.get(event_type, []))
        for handler in handlers:
            try:
                start = datetime.now(UTC)
                handler(event)
                elapsed = (datetime.now(UTC) - start).total_seconds()
                with self._metrics_lock:
                    self._metrics.handler_times[handler.__qualname__] = elapsed
                    self._metrics.handled += 1
            except Exception:
                with self._metrics_lock:
                    self._metrics.errors += 1
                if strict:
                    raise
                logger.exception(
                    "EventBus handler error in {} for {}",
                    handler.__qualname__,
                    event_type,
                )

    def subscribe[E: Event](self, event_type: type[E], handler: Callable[[E], None]) -> None:
        """イベント型に対するハンドラを登録する。

        Args:
            event_type: 購読するイベント型（クラス）。
            handler: イベント発生時に呼び出される関数。
        """
        with self._lock:
            self._subscribers[event_type.__name__].append(handler)

    def unsubscribe[E: Event](self, event_type: type[E], handler: Callable[[E], None]) -> None:
        """ハンドラの登録を解除する。

        Args:
            event_type: 対象のイベント型（クラス）。
            handler: 登録解除するハンドラ関数。
        """
        with self._lock, suppress(ValueError):
            self._subscribers[event_type.__name__].remove(handler)

    async def publish_async(self, event: Event, *, strict: bool = False) -> None:
        """イベントを非同期的に全購読者に配信する。

        非同期ハンドラ（async def）をサポート。
        同期ハンドラは `await asyncio.to_thread()` でラップして実行する。

        Args:
            event: 発行するイベント。
            strict: True の場合、ハンドラ例外を再 raise する。
        """
        if event.timestamp is None:
            event.timestamp = datetime.now(UTC)
        if not event.trace_id:
            event.trace_id = new_trace_id()
        if self._tracer is not None:
            self._tracer.on_event(event)
        event_type = type(event).__name__
        with self._metrics_lock:
            self._metrics.published += 1
        with self._lock:
            handlers = list(self._subscribers.get(event_type, []))
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(event)
                else:
                    await asyncio.to_thread(handler, event)
                with self._metrics_lock:
                    self._metrics.handled += 1
            except Exception:
                with self._metrics_lock:
                    self._metrics.errors += 1
                if strict:
                    raise
                logger.exception(
                    "EventBus async handler error in {} for {}",
                    handler.__qualname__,
                    event_type,
                )
