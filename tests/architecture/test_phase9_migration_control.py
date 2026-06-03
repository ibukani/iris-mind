"""Phase 12 post-deletion architecture guards.

These tests enforce that deleted legacy packages are not reintroduced
and that target packages remain isolated from legacy imports.
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
    "iris.admin",
}

DELETED_LEGACY_PACKAGES: set[str] = {
    "iris/account",
    "iris/agency",
    "iris/event",
    "iris/heartbeat",
    "iris/io",
    "iris/kernel",
    "iris/limbic",
    "iris/llm",
    "iris/memory",
    "iris/room",
    "iris/tools",
    "iris/admin",
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

ENTRYPOINT_GUARD_FILES: set[str] = {
    "main.py",
    "iris/runtime/cli.py",
    "iris/runtime/app.py",
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


# ── Deleted legacy packages must not exist ──


@pytest.mark.parametrize("pkg_dir", sorted(DELETED_LEGACY_PACKAGES))
def test_deleted_legacy_packages_do_not_exist(pkg_dir: str) -> None:
    pkg_path = PROJECT_ROOT / pkg_dir
    assert not pkg_path.exists(), f"Legacy package '{pkg_dir}' still exists — it should have been deleted in Phase 12"


# ── Entrypoint guards ──


def test_main_py_does_not_import_legacy_packages() -> None:
    main_path = PROJECT_ROOT / "main.py"
    assert main_path.is_file()
    tree = ast.parse(main_path.read_text(encoding="utf-8"))
    for imp in _all_imports_from_node(tree):
        for prefix in LEGACY_IMPORT_PREFIXES:
            assert not imp.startswith(prefix), f"main.py imports legacy: {imp}"


def test_main_py_uses_target_runtime() -> None:
    text = (PROJECT_ROOT / "main.py").read_text(encoding="utf-8")
    assert "iris.runtime" in text


@pytest.mark.parametrize("rel_path", sorted(ENTRYPOINT_GUARD_FILES))
def test_entrypoint_no_plugin_manager_or_event_bus(rel_path: str) -> None:
    file_path = PROJECT_ROOT / rel_path
    assert file_path.is_file(), f"Guard file missing: {rel_path}"
    text = file_path.read_text(encoding="utf-8")
    assert "PluginManager" not in text, f"{rel_path} references PluginManager"
    assert "EventBus" not in text, f"{rel_path} references EventBus"


# ── Target package isolation ──


def test_target_packages_do_not_import_legacy_packages() -> None:
    violations: list[str] = []
    for pkg_dir in sorted(TARGET_PACKAGES):
        pkg_path = PROJECT_ROOT / pkg_dir
        if not pkg_path.is_dir():
            continue
        for py_file in sorted(pkg_path.rglob("*.py")):
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
            for imp in _module_body_runtime_imports(tree):
                for prefix in LEGACY_IMPORT_PREFIXES:
                    if imp.startswith(prefix):
                        rel = py_file.relative_to(PROJECT_ROOT)
                        violations.append(f"{imp} from {rel}")
    assert not violations, "Target packages import legacy modules:\n" + "\n".join(violations)


# ── Deletion readiness doc ──


def test_legacy_deletion_readiness_document_exists() -> None:
    doc_path = PROJECT_ROOT / "docs" / "migration" / "legacy-deletion-readiness.md"
    assert doc_path.is_file(), "docs/migration/legacy-deletion-readiness.md is required"
