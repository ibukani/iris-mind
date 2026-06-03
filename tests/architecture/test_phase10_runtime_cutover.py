"""Phase 10 runtime cutover architecture tests.

These tests enforce that the new v1.2.1 runtime entrypoint and its wiring
do not import or depend on legacy Kernel / PluginManager / EventBus modules.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.migration

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

LEGACY_IMPORT_PREFIXES: set[str] = {
    "iris.account",
    "iris.agency",
    "iris.event",
    "iris.heartbeat",
    "iris.io",
    "iris.kernel",
    "iris.limbic",
    "iris.llm",
    "iris.memory",
    "iris.room",
    "iris.tools",
}

PHASE10_GUARD_FILES: set[str] = {
    "iris/runtime/cli.py",
    "iris/runtime/app.py",
    "iris/runtime/wiring/app.py",
    "iris/runtime/wiring/cognitive.py",
    "iris/runtime/wiring/llm.py",
    "iris/runtime/wiring/memory.py",
    "iris/runtime/wiring/features.py",
    "iris/runtime/wiring/presentation.py",
}

PHASE10_GUARD_PACKAGES: set[str] = {
    "iris/runtime",
}


def _module_body_runtime_imports(tree: ast.Module) -> list[str]:
    imports: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.If) and isinstance(node.test, ast.Name) and node.test.id == "TYPE_CHECKING":
            continue
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
    return imports


def _all_imports_from_node(tree: ast.Module) -> list[str]:
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
    return imports


@pytest.mark.parametrize("rel_path", sorted(PHASE10_GUARD_FILES))
def test_runtime_entrypoint_files_do_not_import_legacy_modules(rel_path: str) -> None:
    file_path = PROJECT_ROOT / rel_path
    assert file_path.is_file(), f"Guard file missing: {rel_path}"

    tree = ast.parse(file_path.read_text(encoding="utf-8"))
    violations: list[str] = []
    for imp in _all_imports_from_node(tree):
        for prefix in LEGACY_IMPORT_PREFIXES:
            if imp.startswith(prefix):
                violations.append(f"{imp} from {rel_path}")

    assert not violations, f"New runtime entrypoint '{rel_path}' imports legacy modules:\n" + "\n".join(violations)


@pytest.mark.parametrize("pkg_dir", sorted(PHASE10_GUARD_PACKAGES))
def test_runtime_package_does_not_import_legacy_modules(pkg_dir: str) -> None:
    pkg_path = PROJECT_ROOT / pkg_dir
    assert pkg_path.is_dir(), f"Guard package missing: {pkg_dir}"

    violations: list[str] = []
    for py_file in sorted(pkg_path.rglob("*.py")):
        tree = ast.parse(py_file.read_text(encoding="utf-8"))
        for imp in _module_body_runtime_imports(tree):
            for prefix in LEGACY_IMPORT_PREFIXES:
                if imp.startswith(prefix):
                    rel = py_file.relative_to(PROJECT_ROOT)
                    violations.append(f"{imp} from {rel}")

    assert not violations, f"Package '{pkg_dir}' imports legacy modules:\n" + "\n".join(violations)


def test_runtime_cli_structure_exists() -> None:
    cli_path = PROJECT_ROOT / "iris" / "runtime" / "cli.py"
    assert cli_path.is_file(), "iris/runtime/cli.py must exist as the v1.2.1 target runtime entrypoint"

    text = cli_path.read_text(encoding="utf-8")
    assert "def main()" in text, "cli.py must define a main() function"
    assert "def run_one_turn" in text, "cli.py must define run_one_turn() for testability"


def test_runtime_wiring_app_exists() -> None:
    app_path = PROJECT_ROOT / "iris" / "runtime" / "wiring" / "app.py"
    assert app_path.is_file(), "iris/runtime/wiring/app.py must provide default wiring"


def test_legacy_main_py_still_exists() -> None:
    main_path = PROJECT_ROOT / "main.py"
    assert main_path.is_file(), "Legacy main.py must remain intact during Phase 10"


def test_legacy_entrypoint_not_deleted() -> None:
    kernel_dir = PROJECT_ROOT / "iris" / "kernel"
    event_dir = PROJECT_ROOT / "iris" / "event"
    assert kernel_dir.is_dir(), "Phase 10 must not delete iris/kernel"
    assert event_dir.is_dir(), "Phase 10 must not delete iris/event"
