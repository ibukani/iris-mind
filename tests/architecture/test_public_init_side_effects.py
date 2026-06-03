"""
Architecture tests — public __init__.py content rules.

Ensures __init__.py files are appropriate for their package role:
  - event/__init__.py should be re-exports only (no class/function definitions)
  - kernel/__init__.py should not eagerly import from high-level domain packages
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.legacy_architecture

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# High-level domain packages that kernel should not eagerly import in __init__.py.
# kernel is the DI hub and may import these inside manager.py or other modules,
# but the package-level __init__.py should stay lightweight.
_DOMAIN_PACKAGES = {"iris.agency", "iris.memory", "iris.tools", "iris.limbic", "iris.room", "iris.account"}


def _parse_file(rel_path: str) -> ast.Module | None:
    try:
        return ast.parse((PROJECT_ROOT / rel_path).read_text(encoding="utf-8"))
    except (SyntaxError, FileNotFoundError):
        return None


def test_event_init_is_re_exports_only() -> None:
    """event/__init__.py must contain only imports and __all__ — no business logic."""
    tree = _parse_file("iris/event/__init__.py")
    assert tree is not None, "iris/event/__init__.py not found or unparseable"

    violations = [
        f"{type(n).__name__} '{n.name}'"
        for n in ast.iter_child_nodes(tree)
        if isinstance(n, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    assert not violations, "event/__init__.py defines heavy constructs — should be re-exports only:\n" + "\n".join(
        violations
    )


def test_kernel_init_does_not_eagerly_import_domain_packages() -> None:
    """kernel/__init__.py must not eagerly import from high-level domain packages.

    Kernel is the DI hub and may reference these inside manager.py or other modules,
    but the package-level __init__.py should stay lightweight to avoid tight coupling.
    """
    tree = _parse_file("iris/kernel/__init__.py")
    assert tree is not None, "iris/kernel/__init__.py not found or unparseable"

    violations = [
        node.module
        for node in ast.walk(tree)
        if (
            isinstance(node, ast.ImportFrom)
            and node.module
            and any(node.module.startswith(pkg) for pkg in _DOMAIN_PACKAGES)
        )
    ]
    assert not violations, (
        "kernel/__init__.py eagerly imports domain packages — "
        "move these to deferred imports in manager.py:\n" + "\n".join(violations)
    )
