"""Layer dependency direction, legacy quarantine, and runtime wiring rules for v1.2.1.

Rules enforced:
  1. contracts/ must not import from higher layers.
  2. core/ must not import from any other iris.* module.
  3. cognitive/ must not import from adapters, runtime, or features.
  4. presentation/ must not import from adapters, runtime, or features.
  5. safety/ must not import from adapters, runtime, or features.
  6. New v1.2.1 target modules must not depend on old Plugin/EventBus modules.
  7. runtime/wiring must not contain cognitive policy logic or service locator.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# ── Layer definitions ──────────────────────────────────────────

# Target layers and their forbidden import prefixes.
# Keys are package directories under iris/, values are sets of
# iris.* prefixes that must not be imported by any file in that layer.
LAYER_RULES: dict[str, set[str]] = {
    "iris/contracts": {
        "iris.cognitive",
        "iris.adapters",
        "iris.runtime",
        "iris.features",
        "iris.presentation",
        "iris.safety",
    },
    "iris/core": {
        "iris.cognitive",
        "iris.contracts",
        "iris.adapters",
        "iris.runtime",
        "iris.features",
        "iris.presentation",
        "iris.safety",
        "iris.event",
        "iris.kernel",
        "iris.agency",
        "iris.limbic",
        "iris.llm",
        "iris.memory",
        "iris.room",
        "iris.account",
        "iris.heartbeat",
        "iris.io",
        "iris.tools",
    },
    "iris/cognitive": {
        "iris.adapters",
        "iris.runtime",
        "iris.features",
    },
    "iris/presentation": {
        "iris.adapters",
        "iris.runtime",
        "iris.features",
    },
    "iris/safety": {
        "iris.adapters",
        "iris.runtime",
        "iris.features",
    },
}

# Legacy modules whose import is prohibited from new target modules.
LEGACY_PREFIXES: set[str] = {
    "iris.event",
    "iris.kernel",
    "iris.agency",
    "iris.limbic",
    "iris.llm",
    "iris.memory",
    "iris.room",
    "iris.account",
    "iris.heartbeat",
    "iris.io",
    "iris.tools",
}

# New target layers that must not import from legacy modules.
QUARANTINE_LAYERS: set[str] = {
    "iris/contracts",
    "iris/core",
    "iris/cognitive",
    "iris/presentation",
    "iris/safety",
}

# Permitted exceptions for legacy quarantine: (layer_dir, relative_path, import_prefix, reason)
QUARANTINE_EXCEPTIONS: list[tuple[str, str, str, str]] = []

# Permitted exceptions for layer direction rules: (layer_dir, relative_path, import_prefix, reason)
DIRECTION_EXCEPTIONS: list[tuple[str, str, str, str]] = [
    # e.g. ("iris/contracts", "iris/contracts/foo.py", "iris.cognitive", "TYPE_CHECKING only")
]

# ── Helpers ─────────────────────────────────────────────────────


def _target_path(rel_dir: str) -> Path:
    return PROJECT_ROOT / rel_dir


def _skip_if_missing(rel_dir: str) -> None:
    """Skip test if the target directory does not exist."""
    path = _target_path(rel_dir)
    if not path.is_dir():
        pytest.skip(f"Target layer '{rel_dir}' does not exist yet — tests will activate when created")


def _get_python_files(base: Path) -> list[Path]:
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


def _check_imports_against_forbidden(
    layer_dir: str,
    forbidden: set[str],
    exceptions: list[tuple[str, str, str, str]],
) -> list[str]:
    """Scan layer_dir and return list of violation messages."""
    violations: list[str] = []
    base = _target_path(layer_dir)
    if not base.is_dir():
        return violations

    for filepath in _get_python_files(base):
        rel_path = filepath.relative_to(PROJECT_ROOT).as_posix()
        for imp in _get_imports(filepath):
            if not imp.startswith("iris."):
                continue
            for forbidden_prefix in forbidden:
                if not imp.startswith(forbidden_prefix):
                    continue
                # Check exceptions
                allowed = False
                for exc_layer, exc_file, exc_prefix, _ in exceptions:
                    if exc_layer == layer_dir and exc_file == rel_path and imp.startswith(exc_prefix):
                        allowed = True
                        break
                if not allowed:
                    violations.append(f"  {rel_path}: imports '{imp}' (forbidden for {layer_dir})")
    return violations


# ── 1. Layer dependency direction ──────────────────────────────


@pytest.mark.parametrize(("layer_dir", "forbidden"), sorted(LAYER_RULES.items()))
def test_layer_dependency_direction(layer_dir: str, forbidden: set[str]) -> None:
    """Each layer must not import from higher or sibling layers outside its allowed direction."""
    _skip_if_missing(layer_dir)
    violations = _check_imports_against_forbidden(layer_dir, forbidden, DIRECTION_EXCEPTIONS)
    assert not violations, f"Layer '{layer_dir}' imports from forbidden layers:\n" + "\n".join(violations)


# ── 2. Legacy quarantine ──────────────────────────────────────


@pytest.mark.parametrize("layer_dir", sorted(QUARANTINE_LAYERS))
def test_legacy_module_quarantine(layer_dir: str) -> None:
    """New v1.2.1 target modules must not depend on old Plugin/EventBus modules."""
    _skip_if_missing(layer_dir)
    violations = _check_imports_against_forbidden(layer_dir, LEGACY_PREFIXES, QUARANTINE_EXCEPTIONS)
    assert not violations, f"Layer '{layer_dir}' imports from legacy Plugin/EventBus modules:\n" + "\n".join(violations)


def test_legacy_quarantine_does_not_fail_on_legacy_code() -> None:
    """Legacy modules may still exist without causing failures.

    This test explicitly passes regardless of legacy code presence.
    It documents that the architecture test suite distinguishes
    between legacy migration sources and new target modules.
    """
    legacy_dirs = [d for d in LEGACY_PREFIXES if _target_path(d.replace("iris.", "iris/").replace(".", "/")).is_dir()]
    if legacy_dirs:
        print(f"Legacy modules still present: {sorted(legacy_dirs)} — no quarantine failure expected.")


# ── 3. Runtime wiring rules ────────────────────────────────────


def test_runtime_wiring_no_cognitive_policy() -> None:
    """runtime/wiring must not contain cognitive policy logic or business logic.

    Each file in runtime/wiring/ should only compose dependencies
    via constructor injection.
    """
    wiring_dir = _target_path("iris/runtime/wiring")
    if not wiring_dir.is_dir():
        pytest.skip("Target layer 'iris/runtime/wiring' does not exist yet")

    violations: list[str] = []

    for filepath in _get_python_files(wiring_dir):
        try:
            text = filepath.read_text(encoding="utf-8")
        except Exception:  # noqa: S112
            continue
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node, (ast.ClassDef, ast.AsyncFunctionDef, ast.FunctionDef)) and node.name in {
                "CognitiveCycle",
                "PipelineStep",
                "CognitiveStep",
            }:
                rel = filepath.relative_to(PROJECT_ROOT).as_posix()
                violations.append(f"  {rel}: defines '{node.name}' — wiring should not define domain classes")
            if isinstance(node, ast.FunctionDef) and node.name.startswith("wire_"):
                for child in ast.walk(node):
                    if (
                        isinstance(child, ast.Call)
                        and isinstance(child.func, ast.Attribute)
                        and child.func.attr in {"resolve", "get_service", "locate"}
                    ):
                        rel = filepath.relative_to(PROJECT_ROOT).as_posix()
                        violations.append(f"  {rel}: calls '{child.func.attr}' — service locator forbidden in wiring")

    assert not violations, "runtime/wiring violations found:\n" + "\n".join(violations)


def test_runtime_wiring_not_service_locator() -> None:
    """runtime/wiring must not become a service locator.

    Wiring files should not import PluginManager or resolve functions.
    """
    wiring_dir = _target_path("iris/runtime/wiring")
    if not wiring_dir.is_dir():
        pytest.skip("Target layer 'iris/runtime/wiring' does not exist yet")

    forbidden_imports = {"iris.kernel.manager", "iris.event"}
    violations: list[str] = []

    for filepath in _get_python_files(wiring_dir):
        rel = filepath.relative_to(PROJECT_ROOT).as_posix()
        for imp in _get_imports(filepath):
            for forbidden in forbidden_imports:
                if imp.startswith(forbidden):
                    violations.append(f"  {rel}: imports '{imp}' — wiring should not depend on legacy infrastructure")

    assert not violations, "runtime/wiring service locator violations:\n" + "\n".join(violations)
