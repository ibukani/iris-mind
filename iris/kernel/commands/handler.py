from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from iris.kernel.commands.debug_commands import DebugCommands
from iris.kernel.commands.info_commands import InfoCommands
from iris.kernel.commands.memory_commands import MemoryCommands
from iris.kernel.config import Config

if TYPE_CHECKING:
    from iris.io.session.manager import SessionManager
    from iris.kernel.debug_capture import DebugCapture
    from iris.kernel.diagnostics import SystemDiagnostics
    from iris.llm.bridge import LLMBridge
    from iris.memory.manager import MemoryManager
    from iris.tools.registry import ToolRegistry

from loguru import logger


class CommandHandler:
    def __init__(
        self,
        config: Config | None = None,
        on_shutdown: Callable[[], None] | None = None,
        on_compact: Callable[[], str] | None = None,
        memory: MemoryManager | None = None,
        session_mgr: SessionManager | None = None,
        llm: LLMBridge | None = None,
        registry: ToolRegistry | None = None,
        debug_capture: DebugCapture | None = None,
        diagnostics: SystemDiagnostics | None = None,
    ) -> None:
        self._config = config
        self._on_shutdown = on_shutdown
        self._on_compact = on_compact

        self._mem_cmds = MemoryCommands(memory)
        self._info_cmds = InfoCommands(
            config=config,
            session_mgr=session_mgr,
            llm=llm,
            registry=registry,
        )
        self._debug_cmds = DebugCommands(
            diagnostics=diagnostics,
            debug_capture=debug_capture,
        )

        self._commands: dict[str, Callable[[str], str]] = {
            "help": lambda _: self._help(),
            "status": lambda _: self._status(),
            "shutdown": lambda _: self._shutdown(),
            "compact": lambda _: self._compact(),
            "memory": self._mem_cmds.handle,
            "sessions": lambda _: self._info_cmds.sessions(),
            "ping": lambda _: self._info_cmds.ping(),
            "tools": lambda _: self._info_cmds.tools(),
            "llm": lambda _: self._info_cmds.llm_info(),
            "state": self._debug_cmds._state_cmd,
            "events": self._debug_cmds._events_cmd,
            "health": lambda _: self._debug_cmds._health_cmd(),
            "report": lambda _: self._debug_cmds._report_cmd(),
            "debug": self._debug_cmds.handle,
        }

    def set_shutdown_handler(self, handler: Callable[[], None]) -> None:
        self._on_shutdown = handler

    def set_compact_handler(self, handler: Callable[[], str]) -> None:
        self._on_compact = handler

    def set_memory(self, memory: MemoryManager) -> None:
        self._mem_cmds.set_memory(memory)

    def set_session_mgr(self, session_mgr: SessionManager) -> None:
        self._info_cmds.set_session_mgr(session_mgr)

    def set_llm(self, llm: LLMBridge) -> None:
        self._info_cmds.set_llm(llm)

    def set_registry(self, registry: ToolRegistry) -> None:
        self._info_cmds.set_registry(registry)

    def set_debug_capture(self, debug_capture: DebugCapture) -> None:
        self._debug_cmds.set_debug_capture(debug_capture)

    def set_diagnostics(self, diagnostics: SystemDiagnostics) -> None:
        self._debug_cmds.set_diagnostics(diagnostics)

    def handle(self, name: str, args: str = "") -> str:
        logger.info("CommandHandler: /{} {}", name, args[:100] if args else "")
        handler = self._commands.get(name)
        if handler is None:
            return f"Unknown command: /{name}"
        return handler(args)

    def _help(self) -> str:
        return (
            "Available commands:\n"
            "  /help               Show this help\n"
            "  /status             Show kernel status\n"
            "  /shutdown           Graceful shutdown\n"
            "  /compact            Compact context\n"
            "  /memory recent [n]  Show recent episodic memories\n"
            "  /memory search <q>  Search semantic memory\n"
            "  /memory clear [type] Clear episodic/semantic memory\n"
            "  /sessions           Show active sessions\n"
            "  /ping               Check LLM health\n"
            "  /tools               List registered tools\n"
            "  /llm                Show LLM config\n"
            "  /state [<path>]     System state (alias: /debug state)\n"
            "  /events [n]         Recent events (alias: /debug events)\n"
            "  /health             Health check (alias: /debug health)\n"
            "  /report             Debug report (alias: /debug report)\n"
            "  /debug              Debug subsystem (/debug help for subcommands)\n"
            "  /debug on|off       Toggle LLM prompt/response capture\n"
            "  /debug list|last    List or show latest LLM capture\n"
            "  /debug show <id>    Show specific LLM capture\n"
            "  /debug dump         Write all captures to files"
        )

    def _status(self) -> str:
        cfg = self._config
        if cfg is None:
            return "Kernel running (no config)"
        lines = [
            f"Models: {[m.name for m in cfg.model.models]}",
            f"Session: {cfg.session.host}:{cfg.session.port}",
            f"Memory: episodic={cfg.memory.episodic_max_entries}, semantic={cfg.memory.semantic_max_entries}",
        ]
        return "\n".join(lines)

    def _shutdown(self) -> str:
        if self._on_shutdown:
            self._on_shutdown()
        return "Shutting down..."

    def _compact(self) -> str:
        if self._on_compact:
            return self._on_compact()
        return "Compact handler not available"
