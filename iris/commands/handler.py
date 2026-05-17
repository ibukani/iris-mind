from __future__ import annotations

import logging
from collections.abc import Callable

from iris.kernel.config import Config

logger = logging.getLogger(__name__)


class CommandHandler:
    def __init__(
        self,
        config: Config | None = None,
        on_shutdown: Callable[[], None] | None = None,
    ) -> None:
        self._config = config
        self._on_shutdown = on_shutdown

    def set_shutdown_handler(self, handler: Callable[[], None]) -> None:
        self._on_shutdown = handler

    def handle(self, name: str, args: str = "") -> str:
        if name == "help":
            return "Available: /help, /status, /shutdown"
        if name == "status":
            return "Kernel running"
        if name == "shutdown":
            if self._on_shutdown:
                self._on_shutdown()
            return "Shutting down..."
        return f"Unknown command: /{name}"
