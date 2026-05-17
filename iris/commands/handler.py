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
        on_compact: Callable[[], str] | None = None,
    ) -> None:
        self._config = config
        self._on_shutdown = on_shutdown
        self._on_compact = on_compact

    def set_shutdown_handler(self, handler: Callable[[], None]) -> None:
        self._on_shutdown = handler

    def set_compact_handler(self, handler: Callable[[], str]) -> None:
        self._on_compact = handler

    def handle(self, name: str, args: str = "") -> str:
        if name == "help":
            return self._help()
        if name == "status":
            return self._status()
        if name == "shutdown":
            return self._shutdown()
        if name == "compact":
            return self._compact()
        return f"Unknown command: /{name}"

    def _help(self) -> str:
        return (
            "Available commands:\n"
            "  /help               Show this help\n"
            "  /status             Show kernel status\n"
            "  /shutdown           Graceful shutdown\n"
            "  /compact            Compact context (summarize history)"
        )

    def _status(self) -> str:
        cfg = self._config
        if cfg is None:
            return "Kernel running (no config)"
        return (
            f"Model: {cfg.model.provider} ({cfg.model.get_model('default')})\n"
            f"Session: {cfg.session.host}:{cfg.session.port}\n"
            f"Memory: episodic={cfg.memory.episodic_max_entries}, semantic={cfg.memory.semantic_max_entries}"
        )

    def _shutdown(self) -> str:
        if self._on_shutdown:
            self._on_shutdown()
        return "Shutting down..."

    def _compact(self) -> str:
        if self._on_compact:
            return self._on_compact()
        return "Compact handler not available"
