from __future__ import annotations

import logging
import threading
from typing import Protocol

from iris.event.event import TimerTick

from ..config import Config
from .factory import KernelContext, KernelFactory

logger = logging.getLogger(__name__)


class KernelProcessProtocol(Protocol):
    def start(self) -> None: ...
    def shutdown(self) -> None: ...

    @property
    def shutdown_requested(self) -> bool: ...


class KernelProcess:
    def __init__(self, config: Config) -> None:
        self._config = config
        self._ctx: KernelContext | None = None
        self._timer_thread: threading.Thread | None = None

    @property
    def shutdown_requested(self) -> bool:
        return self._ctx is not None and self._ctx.shutdown_requested

    def start(self) -> None:
        logger.info("KernelProcess: starting")

        self._ctx = KernelFactory.build(self._config)

        host = self._config.session.host
        port = self._config.session.port
        self._ctx.io.start(host=host, port=port)

        self._start_timer()
        logger.info("KernelProcess: started")

    def shutdown(self) -> None:
        logger.info("KernelProcess: shutting down")

        ctx = self._ctx
        if ctx is None:
            logger.info("KernelProcess: shutdown complete (was not started)")
            return

        ctx.shutdown_requested = True
        ctx.io.stop()

        logger.info("KernelProcess: shutdown complete")

    def _start_timer(self) -> None:
        ctx = self._ctx
        if ctx is None:
            return
        interval = self._config.proactive.check_interval_sec
        tick_count: list[int] = [0]

        def _loop() -> None:
            while not ctx.shutdown_requested:
                ctx.event_bus.publish(TimerTick(
                    timestamp=None,
                    source="kernel",
                    tick_count=tick_count[0],
                ))
                tick_count[0] += 1
                threading.Event().wait(interval)

        self._timer_thread = threading.Thread(target=_loop, daemon=True, name="kernel-timer")
        self._timer_thread.start()
        logger.info("KernelProcess: timer started (interval=%.1fs)", interval)
