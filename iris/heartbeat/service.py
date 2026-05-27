from __future__ import annotations

import threading

from loguru import logger

from iris.event.event_bus import EventBus
from iris.event.event_types import TimerTick


class TimerService:
    def __init__(self, event_bus: EventBus, interval: float) -> None:
        self._event_bus = event_bus
        self._interval = interval
        self._shutdown = threading.Event()
        self._tick_count = 0
        self._thread: threading.Thread | None = None

    @property
    def tick_count(self) -> int:
        return self._tick_count

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self._thread is not None:
            return
        self._shutdown.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="heartbeat")
        self._thread.start()
        logger.info("TimerService: started (interval={:.1f}s)", self._interval)

    def stop(self, timeout: float = 2.0) -> None:
        self._shutdown.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None
        logger.info("TimerService: stopped")

    def _loop(self) -> None:
        while not self._shutdown.is_set():
            self._event_bus.publish(
                TimerTick(
                    timestamp=None,
                    source="heartbeat",
                    tick_count=self._tick_count,
                )
            )
            self._tick_count += 1
            self._shutdown.wait(self._interval)
