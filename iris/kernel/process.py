from __future__ import annotations

import threading
from typing import Protocol

from loguru import logger

from iris.event.event_types import TimerTick

from .config import Config
from .manager import PluginManager


class KernelProcessProtocol(Protocol):
    def start(self) -> None: ...
    def shutdown(self) -> None: ...

    @property
    def shutdown_requested(self) -> bool: ...


class KernelProcess:
    def __init__(self, config: Config, debug: bool = False) -> None:
        self._config = config
        self._debug = debug
        self._manager: PluginManager | None = None
        self._timer_thread: threading.Thread | None = None

    @property
    def shutdown_requested(self) -> bool:
        return self._manager is not None and self._manager.shutdown_requested

    @property
    def cmd_handler(self) -> object | None:
        return self._manager.cmd_handler if self._manager else None

    def start(self) -> None:
        logger.info("KernelProcess: starting")

        self._manager = PluginManager(self._config, debug=self._debug)
        self._manager.discover_and_build_all()

        host = self._config.session.host
        port = self._config.session.port
        io_mgr = self._manager.resolve("IOManager")
        io_mgr.start(host=host, port=port)

        self._manager.start_all()
        self._start_timer()
        logger.info("KernelProcess: started")

    def shutdown(self) -> None:
        logger.info("KernelProcess: shutting down")

        manager = self._manager
        if manager is None:
            logger.info("KernelProcess: shutdown complete (was not started)")
            return

        manager.request_shutdown()
        agency = manager.resolve_optional("AgencyManager")
        if agency is not None and hasattr(agency, "shutdown"):
            agency.shutdown()
        manager.stop_all()
        logger.info("KernelProcess: shutdown complete")

    def _start_timer(self) -> None:
        manager = self._manager
        if manager is None:
            return
        interval = self._config.proactive.check_interval_sec
        tick_count: list[int] = [0]

        def _loop() -> None:
            while not manager.shutdown_requested:
                manager.event_bus.publish(
                    TimerTick(
                        timestamp=None,
                        source="kernel",
                        tick_count=tick_count[0],
                    )
                )
                tick_count[0] += 1
                threading.Event().wait(interval)

        self._timer_thread = threading.Thread(target=_loop, daemon=True, name="kernel-timer")
        self._timer_thread.start()
        logger.info("KernelProcess: timer started (interval={:.1f}s)", interval)
