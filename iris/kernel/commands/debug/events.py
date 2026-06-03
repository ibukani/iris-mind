from __future__ import annotations

from contextlib import suppress
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from iris.kernel.diagnostics import SystemDiagnostics


def handle_events(diagnostics: SystemDiagnostics | None, args: str) -> str:
    if diagnostics is None:
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
    tracer = getattr(diagnostics, "_tracer", None)
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
