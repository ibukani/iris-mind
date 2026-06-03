from __future__ import annotations

from typing import TYPE_CHECKING

from .capture import handle_capture
from .events import handle_events
from .health import handle_health, handle_report
from .state import handle_state

if TYPE_CHECKING:
    from iris.kernel.debug_capture import DebugCapture
    from iris.kernel.diagnostics import SystemDiagnostics


class DebugCommands:
    def __init__(
        self,
        diagnostics: SystemDiagnostics | None = None,
        debug_capture: DebugCapture | None = None,
    ) -> None:
        self._diagnostics = diagnostics
        self._debug_capture = debug_capture

    def set_diagnostics(self, diagnostics: SystemDiagnostics) -> None:
        self._diagnostics = diagnostics

    def set_debug_capture(self, debug_capture: DebugCapture) -> None:
        self._debug_capture = debug_capture

    def handle(self, args: str) -> str:
        parts = args.strip().split(maxsplit=1)
        sub = parts[0].lower() if parts else ""
        rest = parts[1] if len(parts) > 1 else ""

        if sub == "state":
            return handle_state(self._diagnostics, rest)
        if sub == "events":
            return handle_events(self._diagnostics, rest)
        if sub == "health":
            return handle_health(self._diagnostics)
        if sub == "report":
            return handle_report(self._diagnostics)

        result = handle_capture(self._debug_capture, sub, rest)
        if result is not None:
            return result

        return self._help()

    def _state_cmd(self, args: str) -> str:
        return handle_state(self._diagnostics, args)

    def _events_cmd(self, args: str) -> str:
        return handle_events(self._diagnostics, args)

    def _health_cmd(self) -> str:
        return handle_health(self._diagnostics)

    def _report_cmd(self) -> str:
        return handle_report(self._diagnostics)

    def _help(self) -> str:
        return (
            "Debug subcommands:\n"
            "  state [<path>] [--history] [--json]   System state query\n"
            "  events [n] [--type=TYPE]              Recent events\n"
            "  health                                 Health check\n"
            "  report                                 Generate Markdown report\n"
            "  capture on|off|list|last|show|dump     LLM prompt/response capture"
        )
