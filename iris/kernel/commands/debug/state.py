from __future__ import annotations

from typing import TYPE_CHECKING

import orjson

from iris.kernel.commands.state_utils import _format_state, _parse_state_args

if TYPE_CHECKING:
    from iris.kernel.diagnostics import SystemDiagnostics


def handle_state(diagnostics: SystemDiagnostics | None, args: str) -> str:
    if diagnostics is None:
        return "Diagnostics not available"
    sa = _parse_state_args(args)
    if sa.history:
        return format_state_history(diagnostics, sa.path, sa.n)
    state = diagnostics.query(sa.path)
    if state is None:
        return f"Path not found: '{sa.path}'" if sa.path else "No state available"
    if sa.as_json:
        return str(orjson.dumps(state, option=orjson.OPT_INDENT_2).decode("utf-8"))
    return _format_state(state, sa.path)


def format_state_history(diagnostics: SystemDiagnostics, path: str, n: int) -> str:
    result = diagnostics.query(path, history=True, n=n)
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
