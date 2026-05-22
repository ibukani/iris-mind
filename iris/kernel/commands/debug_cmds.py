from __future__ import annotations

from collections.abc import Callable
from contextlib import suppress
from typing import TYPE_CHECKING

from iris.kernel.commands.state_utils import _format_state, _parse_state_args

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

        delegations: dict[str, Callable[[str], str]] = {
            "state": self._state_cmd,
            "events": self._events_cmd,
            "health": lambda _: self._health_cmd(),
            "report": lambda _: self._report_cmd(),
        }
        handler = delegations.get(sub)
        if handler is not None:
            return handler(rest)

        if sub == "on":
            if not self._debug_capture:
                return "DebugCapture not available"
            self._debug_capture.set_enabled(True)
            return "Debug capture enabled"

        if sub == "off":
            if not self._debug_capture:
                return "DebugCapture not available"
            self._debug_capture.set_enabled(False)
            return "Debug capture disabled"

        if sub == "help" or not sub:
            return self._help()

        if not self._debug_capture:
            return "DebugCapture not available. Available: state, events, health, report"

        if not self._debug_capture.enabled:
            return "Debug capture is disabled (use /debug on first). Available: state, events, health, report"

        if sub == "list":
            return self._debug_capture.list_captures()

        if sub == "last":
            entries = self._debug_capture.last()
            if not entries:
                return "No captures"
            return "\n\n".join(e.format() for e in entries)

        if sub in ("show", "get"):
            try:
                entry_id = int(rest)
            except (ValueError, TypeError):
                return "Usage: /debug show <id>"
            return self._debug_capture.show(entry_id)

        if sub == "dump":
            written = self._debug_capture.dump_all()
            if not written:
                return "No captures to dump"
            return f"Wrote {len(written)} file(s):\n" + "\n".join(str(p) for p in written)

        return self._help()

    def _state_cmd(self, args: str) -> str:
        diag = self._diagnostics
        if diag is None:
            return "Diagnostics not available"
        sa = _parse_state_args(args)
        if sa.history:
            return self._format_state_history(diag, sa.path, sa.n)
        state = diag.query(sa.path)
        if state is None:
            return f"Path not found: '{sa.path}'" if sa.path else "No state available"
        if sa.as_json:
            import json

            return json.dumps(state, ensure_ascii=False, indent=2)
        return _format_state(state, sa.path)

    def _format_state_history(self, diag: SystemDiagnostics, path: str, n: int) -> str:
        result = diag.query(path, history=True, n=n)
        if result is None:
            return "No history available (tracer not enabled)"
        if not result:
            return f"No history for '{path}'"
        lines = []
        for e in result:
            ts = e.get("timestamp", "")
            trigger = e.get("trigger", "")
            data = e.get("data", {})
            data_str = ", ".join(f"{k}={v}" for k, v in (data or {}).items())
            lines.append(f"[{ts}] {trigger} → {data_str}")
        return "\n".join(lines)

    def _events_cmd(self, args: str) -> str:
        diag = self._diagnostics
        if diag is None:
            return "Diagnostics not available"
        parts = args.strip().split()
        n = 10
        type_filter = None
        for p in parts:
            if p.startswith("--type="):
                type_filter = p[7:]
            elif p.startswith("--n="):
                with suppress(ValueError):
                    n = int(p[4:])
            elif p.isdigit():
                n = int(p)
        tracer = getattr(diag, "_tracer", None)
        if tracer is None or not tracer.enabled:
            return "Event tracing not enabled"
        events = tracer.recent(n, type_filter=type_filter)
        if not events:
            return "No events"
        lines = []
        for e in events:
            ts = e.get("timestamp", "")
            et = e.get("type", "")
            src = e.get("source", "")
            cat = e.get("category", "")
            extra = f" [{cat}]" if cat else ""
            tid = e.get("trace_id", "")[:8]
            lines.append(f"[{ts}] {et} <{src}>{extra} tid={tid}")
        return "\n".join(lines)

    def _health_cmd(self) -> str:
        diag = self._diagnostics
        if diag is None:
            return "Diagnostics not available"
        h = diag.health()
        if not h:
            return "Health check: no data"
        lines = []
        for k, v in h.items():
            if v.startswith("OK"):
                lines.append(f"  ✓ {k}: {v}")
            elif v == "NOT_LOADED":
                lines.append(f"  ○ {k}: not loaded")
            else:
                lines.append(f"  ✗ {k}: {v}")
        return "Health check:\n" + "\n".join(lines)

    def _report_cmd(self) -> str:
        diag = self._diagnostics
        if diag is None:
            return "Diagnostics not available"
        return diag.generate_report()

    def _help(self) -> str:
        return (
            "Debug subcommands:\n"
            "  state [<path>] [--history] [--json]   System state query\n"
            "  events [n] [--type=TYPE]              Recent events\n"
            "  health                                 Health check\n"
            "  report                                 Generate Markdown report\n"
            "  capture on|off|list|last|show|dump     LLM prompt/response capture"
        )
