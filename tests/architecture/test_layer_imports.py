"""
Architecture tests — cross-layer import rules.

Enforces dependency direction between iris subpackages.
Known exceptions are documented with rationale and migration path.
"""

from __future__ import annotations

import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# Packages that must not import specific higher-level packages.
# Keys are package directories, values are sets of forbidden iris.* prefixes.
FORBIDDEN_IMPORTS: dict[str, set[str]] = {
    "iris/heartbeat": {"iris.agency", "iris.memory", "iris.io", "iris.limbic"},
    "iris/llm": {"iris.agency", "iris.memory", "iris.tools", "iris.io", "iris.room", "iris.account", "iris.limbic"},
    "iris/tools": {"iris.agency"},
    "iris/io": {"iris.agency", "iris.memory"},
    "iris/memory": {"iris.agency", "iris.io"},
    "iris/room": {"iris.agency", "iris.memory", "iris.io", "iris.limbic", "iris.tools", "iris.llm"},
    "iris/account": {"iris.agency", "iris.memory", "iris.io", "iris.limbic", "iris.room", "iris.tools", "iris.llm"},
    "iris/limbic": {"iris.agency"},
}

# Documented exceptions: (package_dir, relative_filepath, import_prefix, reason)
EXCEPTIONS: list[tuple[str, str, str, str]] = [
    (
        "iris/tools",
        "iris/tools/__init__.py",
        "iris.agency",
        "Deferred ToolEngine import in ToolsPlugin.init() — migration: move ToolEngine to iris.tools package",
    ),
    (
        "iris/limbic",
        "iris/limbic/orchestrator.py",
        "iris.agency",
        "TYPE_CHECKING + deferred ModulationState import — read-only reference",
    ),
    (
        "iris/memory",
        "iris/memory/handler.py",
        "iris.io.events",
        "IO domain event types moved from iris.event.event_types to iris.io.events — lightweight event definitions, no io runtime dependency",
    ),
    (
        "iris/memory",
        "iris/memory/events/proactive_trigger.py",
        "iris.io.events",
        "IO domain event types moved from iris.event.event_types to iris.io.events — lightweight event definitions, no io runtime dependency",
    ),
    (
        "iris/room",
        "iris/room/dispatcher.py",
        "iris.io.events",
        "IO domain event types moved from iris.event.event_types to iris.io.events — lightweight event definitions, no io runtime dependency",
    ),
    (
        "iris/room",
        "iris/room/handler.py",
        "iris.io.events",
        "IO domain event types moved from iris.event.event_types to iris.io.events — lightweight event definitions, no io runtime dependency",
    ),
    (
        "iris/account",
        "iris/account/dispatcher.py",
        "iris.io.events",
        "IO domain event types moved from iris.event.event_types to iris.io.events — lightweight event definitions, no io runtime dependency",
    ),
]


def _get_python_files(package_dir: str) -> list[Path]:
    base = PROJECT_ROOT / package_dir
    return sorted(base.rglob("*.py"))


def _get_imports(filepath: Path) -> list[str]:
    try:
        tree = ast.parse(filepath.read_text(encoding="utf-8"))
    except SyntaxError:
        return []
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
    return imports


def _get_iris_imports(package_dir: str) -> list[tuple[Path, str]]:
    results: list[tuple[Path, str]] = []
    for filepath in _get_python_files(package_dir):
        results.extend((filepath, imp) for imp in _get_imports(filepath) if imp.startswith("iris."))
    return results


def _is_allowed_exception(package_dir: str, rel_path: str, imp: str) -> bool:
    for exc_pkg, exc_file, exc_prefix, _ in EXCEPTIONS:
        if exc_pkg == package_dir and exc_file == rel_path and imp.startswith(exc_prefix):
            return True
    return False


def test_layer_import_rules() -> None:
    violations: list[str] = []
    exception_notes: list[str] = []

    for package_dir, forbidden in FORBIDDEN_IMPORTS.items():
        for filepath, imp in _get_iris_imports(package_dir):
            for forbidden_prefix in forbidden:
                if imp.startswith(forbidden_prefix):
                    rel_path = str(filepath.relative_to(PROJECT_ROOT))
                    if _is_allowed_exception(package_dir, rel_path, imp):
                        exc_reason = next(
                            r for p, f, px, r in EXCEPTIONS if p == package_dir and f == rel_path and imp.startswith(px)
                        )
                        exception_notes.append(f"  ALLOWED: {rel_path} -> {imp} ({exc_reason})")
                    else:
                        violations.append(f"  {rel_path}: imports '{imp}' (forbidden for {package_dir})")

    if exception_notes:
        print("Documented exceptions:\n" + "\n".join(exception_notes))

    assert not violations, "Layer import violations found:\n" + "\n".join(violations)
