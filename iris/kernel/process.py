from __future__ import annotations

from typing import Protocol

from loguru import logger

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

    @property
    def shutdown_requested(self) -> bool:
        return self._manager is not None and self._manager.shutdown_requested

    @property
    def cmd_handler(self) -> object | None:
        return self._manager.cmd_handler if self._manager else None

    def start(self) -> None:
        logger.info("KernelProcess: starting")

        self._manager = PluginManager(self._config, debug=self._debug)
        try:
            self._manager.discover_and_build_all()

            from iris.io.manager import IOManager

            host = self._config.session.host
            port = self._config.session.port
            io_mgr = self._manager.resolve(IOManager)
            io_mgr.start(host=host, port=port)

            self._manager.start_all()
        except Exception:
            logger.exception("KernelProcess: start failed, cleaning up")
            self._cleanup()
            raise
        logger.info("KernelProcess: started")

    def _cleanup(self) -> None:
        manager = self._manager
        if manager is None:
            return
        try:
            manager.stop_all()
        except Exception:
            logger.exception("KernelProcess: cleanup error")
        self._manager = None

    def shutdown(self) -> None:
        logger.info("KernelProcess: shutting down")

        manager = self._manager
        if manager is None:
            logger.info("KernelProcess: shutdown complete (was not started)")
            return

        manager.request_shutdown()
        from iris.agency.manager import AgencyManager

        agency = manager.resolve_optional(AgencyManager)
        if agency is not None and hasattr(agency, "shutdown"):
            agency.shutdown()
        self._cleanup()
        logger.info("KernelProcess: shutdown complete")
