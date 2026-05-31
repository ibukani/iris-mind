from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from iris.kernel.diagnostics import SystemDiagnostics


def handle_health(diagnostics: SystemDiagnostics | None) -> str:
    if diagnostics is None:
        return "Diagnostics not available"
    h = diagnostics.health()
    if not h:
        return "Health check: no data"
    lines = []
    for k, v in h.items():
        if v.startswith("OK"):
            lines.append(f"  \u2713 {k}: {v}")
        elif v == "NOT_LOADED":
            lines.append(f"  \u25cb {k}: not loaded")
        else:
            lines.append(f"  \u2717 {k}: {v}")
    return "Health check:\n" + "\n".join(lines)


def handle_report(diagnostics: SystemDiagnostics | None) -> str:
    if diagnostics is None:
        return "Diagnostics not available"
    return diagnostics.generate_report()
