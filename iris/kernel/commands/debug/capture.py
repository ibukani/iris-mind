from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from iris.kernel.debug_capture import DebugCapture


def handle_capture(
    debug_capture: DebugCapture | None,
    sub: str,
    rest: str,
) -> str | None:
    """Handle capture subcommands. Returns str for capture commands, None otherwise."""
    if sub == "on":
        if not debug_capture:
            return "DebugCapture not available"
        debug_capture.set_enabled(True)
        return "Debug capture enabled"

    if sub == "off":
        if not debug_capture:
            return "DebugCapture not available"
        debug_capture.set_enabled(False)
        return "Debug capture disabled"

    if sub in ("help", "state", "events", "health", "report") or not sub:
        return None

    if not debug_capture:
        return "DebugCapture not available. Available: state, events, health, report"

    if not debug_capture.enabled:
        return "Debug capture is disabled (use /debug on first). Available: state, events, health, report"

    if sub == "list":
        return debug_capture.list_captures()

    if sub == "last":
        entries = debug_capture.last()
        if not entries:
            return "No captures"
        return "\n\n".join(e.format() for e in entries)

    if sub in ("show", "get"):
        try:
            entry_id = int(rest)
        except (ValueError, TypeError):
            return "Usage: /debug show <id>"
        return debug_capture.show(entry_id)

    if sub == "dump":
        written = debug_capture.dump_all()
        if not written:
            return "No captures to dump"
        return f"Wrote {len(written)} file(s):\n" + "\n".join(str(p) for p in written)

    return None
