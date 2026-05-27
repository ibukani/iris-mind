from __future__ import annotations

import threading
import time

from loguru import logger

from iris.event.event_bus import EventBus
from iris.event.event_types import TimerTick


class TimerService:
    def __init__(self, event_bus: EventBus, interval: float) -> None:
        self._event_bus = event_bus
        self._interval = interval
        self._shutdown = threading.Event()
        self._reset = threading.Event()
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
        self._reset.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="heartbeat")
        self._thread.start()
        logger.info("TimerService: started (interval={:.1f}s)", self._interval)

    def stop(self, timeout: float = 2.0) -> None:
        self._shutdown.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None
        logger.info("TimerService: stopped")

    def tick(self) -> None:
        """Publish a TimerTick immediately, outside the regular cycle."""
        self._event_bus.publish(
            TimerTick(
                timestamp=None,
                source="heartbeat:manual",
                tick_count=-1,
            )
        )

    def reset(self) -> None:
        """Skip remaining wait; next regular tick fires after one full interval."""
        self._reset.set()

    def schedule_tick(self, delay: float) -> None:
        """Schedule a one-shot TimerTick after *delay* seconds."""
        timer = threading.Timer(delay, self.tick)
        timer.daemon = True
        timer.start()

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
            self._wait_for_interval()

    def _wait_for_interval(self) -> None:
        deadline = time.monotonic() + self._interval
        while not self._shutdown.is_set():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            chunk = min(remaining, 0.05)
            if self._reset.wait(timeout=chunk):
                self._reset.clear()
                return
