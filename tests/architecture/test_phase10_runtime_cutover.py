"""Phase 11 runtime cutover architecture tests.

These tests enforce:
  - main.py delegates to target runtime and does not import legacy Kernel/EventBus
  - Target runtime entrypoint and wiring do not import legacy packages
  - Target tests do not require legacy fixtures
  - No default runtime path uses PluginManager/EventBus
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

RUNTIME_GUARD_FILES: set[str] = {
    "iris/runtime/cli.py",
    "iris/runtime/app.py",
    "iris/runtime/wiring/app.py",
    "iris/runtime/wiring/cognitive.py",
    "iris/runtime/wiring/llm.py",
    "iris/runtime/wiring/memory.py",
    "iris/runtime/wiring/features.py",
    "iris/runtime/wiring/presentation.py",
}

ENTRYPOINT_GUARD_FILES: set[str] = {
    "main.py",
}

TARGET_PACKAGES: set[str] = {
    "iris/core",
    "iris/contracts",
    "iris/cognitive",
    "iris/presentation",
    "iris/safety",
    "iris/features",
    "iris/adapters",
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


def _check_file_imports(file_path: Path, prefixes: set[str]) -> list[str]:
    violations: list[str] = []
    tree = ast.parse(file_path.read_text(encoding="utf-8"))
    for imp in _all_imports_from_node(tree):
        for prefix in prefixes:
            if imp.startswith(prefix):
                violations.append(f"{imp} from {file_path.relative_to(PROJECT_ROOT)}")
    return violations


# ── Entrypoint guards ──


def test_main_py_does_not_import_iris_kernel() -> None:
    main_path = PROJECT_ROOT / "main.py"
    assert main_path.is_file(), "main.py must exist as the target runtime entrypoint"

    tree = ast.parse(main_path.read_text(encoding="utf-8"))
    imports = _all_imports_from_node(tree)
    for imp in imports:
        assert not imp.startswith("iris.kernel"), f"main.py imports iris.kernel: {imp}"


def test_main_py_does_not_import_iris_event() -> None:
    main_path = PROJECT_ROOT / "main.py"
    assert main_path.is_file(), "main.py must exist"

    tree = ast.parse(main_path.read_text(encoding="utf-8"))
    imports = _all_imports_from_node(tree)
    for imp in imports:
        assert not imp.startswith("iris.event"), f"main.py imports iris.event: {imp}"


def test_main_py_does_not_import_legacy_packages() -> None:
    main_path = PROJECT_ROOT / "main.py"
    assert main_path.is_file(), "main.py must exist"

    violations = _check_file_imports(main_path, LEGACY_IMPORT_PREFIXES)
    assert not violations, "main.py imports legacy packages:\n" + "\n".join(violations)


def test_main_py_uses_target_runtime() -> None:
    main_path = PROJECT_ROOT / "main.py"
    text = main_path.read_text(encoding="utf-8")
    assert "iris.runtime" in text, "main.py must delegate to target runtime"


# ── Runtime file guards ──


@pytest.mark.parametrize("rel_path", sorted(RUNTIME_GUARD_FILES))
def test_runtime_entrypoint_files_do_not_import_legacy_modules(rel_path: str) -> None:
    file_path = PROJECT_ROOT / rel_path
    assert file_path.is_file(), f"Guard file missing: {rel_path}"

    violations = _check_file_imports(file_path, LEGACY_IMPORT_PREFIXES)
    assert not violations, f"Runtime file '{rel_path}' imports legacy modules:\n" + "\n".join(violations)


# ── Package-level guards ──


@pytest.mark.parametrize("pkg_dir", sorted(TARGET_PACKAGES))
def test_target_package_does_not_import_legacy_modules(pkg_dir: str) -> None:
    pkg_path = PROJECT_ROOT / pkg_dir
    if not pkg_path.is_dir():
        pytest.skip(f"Target package '{pkg_dir}' does not exist yet")

    violations: list[str] = []
    for py_file in sorted(pkg_path.rglob("*.py")):
        tree = ast.parse(py_file.read_text(encoding="utf-8"))
        for imp in _module_body_runtime_imports(tree):
            for prefix in LEGACY_IMPORT_PREFIXES:
                if imp.startswith(prefix):
                    rel = py_file.relative_to(PROJECT_ROOT)
                    violations.append(f"{imp} from {rel}")

    assert not violations, f"Package '{pkg_dir}' imports legacy modules:\n" + "\n".join(violations)


# ── Structure guards ──


def test_runtime_cli_structure_exists() -> None:
    cli_path = PROJECT_ROOT / "iris" / "runtime" / "cli.py"
    assert cli_path.is_file(), "iris/runtime/cli.py must exist"

    text = cli_path.read_text(encoding="utf-8")
    assert "def main()" in text, "cli.py must define a main() function"
    assert "def run_one_turn" in text, "cli.py must define run_one_turn() for testability"


def test_runtime_wiring_app_exists() -> None:
    app_path = PROJECT_ROOT / "iris" / "runtime" / "wiring" / "app.py"
    assert app_path.is_file(), "iris/runtime/wiring/app.py must provide default wiring"


def test_main_py_exists() -> None:
    main_path = PROJECT_ROOT / "main.py"
    assert main_path.is_file(), "main.py must exist as the entrypoint"


# ── No PluginManager/EventBus in target path ──


@pytest.mark.parametrize("rel_path", sorted({"main.py"} | RUNTIME_GUARD_FILES))
def test_entrypoint_files_no_plugin_manager_or_event_bus(rel_path: str) -> None:
    file_path = PROJECT_ROOT / rel_path
    assert file_path.is_file(), f"File missing: {rel_path}"

    text = file_path.read_text(encoding="utf-8")
    assert "PluginManager" not in text, f"{rel_path} references PluginManager"
    assert "EventBus" not in text, f"{rel_path} references EventBus"
