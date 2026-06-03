"""Phase 9 migration-control tests.

These tests do not migrate runtime features by themselves.  They enforce the
controls required before safe feature-by-feature migration and deletion:
  - target packages must not import legacy packages;
  - target test collection helpers must be free of eager legacy imports;
  - legacy tests must be explicitly marked;
  - the deletion-readiness document must track each legacy package.
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

LEGACY_PACKAGES: set[str] = {
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
}

LEGACY_ARCHITECTURE_TESTS: set[str] = {
    "tests/architecture/test_dependency_rules.py",
    "tests/architecture/test_handler_only_subscriptions.py",
    "tests/architecture/test_layer_imports.py",
    "tests/architecture/test_no_service_locator.py",
    "tests/architecture/test_plugin_boundaries.py",
    "tests/architecture/test_public_init_side_effects.py",
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

LEGACY_TEST_DIRS: set[str] = {
    "tests/agency",
    "tests/kernel",
    "tests/room",
    "tests/llm",
    "tests/memory",
    "tests/limbic",
    "tests/account",
    "tests/tools",
}


def _imports_from_node(node: ast.AST) -> list[str]:
    imports: list[str] = []
    for child in ast.walk(node):
        if isinstance(child, ast.Import):
            imports.extend(alias.name for alias in child.names)
        elif isinstance(child, ast.ImportFrom) and child.module:
            imports.append(child.module)
    return imports


def _is_type_checking_guard(node: ast.AST) -> bool:
    if not isinstance(node, ast.If):
        return False
    test = node.test
    return isinstance(test, ast.Name) and test.id == "TYPE_CHECKING"


def _module_body_runtime_imports(tree: ast.Module) -> list[str]:
    """Return only runtime imports executed directly at module import time."""
    imports: list[str] = []
    for node in tree.body:
        if _is_type_checking_guard(node):
            continue
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
    return imports


def _has_legacy_architecture_mark(tree: ast.Module) -> bool:
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == "pytestmark" for target in node.targets):
            continue
        value = node.value
        if isinstance(value, ast.Attribute) and value.attr == "legacy_architecture":
            return True
        if isinstance(value, ast.List):
            for elt in value.elts:
                if isinstance(elt, ast.Attribute) and elt.attr == "legacy_architecture":
                    return True
    return False


def _has_legacy_mark(tree: ast.Module) -> bool:
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == "pytestmark" for target in node.targets):
            continue
        value = node.value
        if isinstance(value, ast.Attribute) and value.attr == "legacy":
            return True
        if isinstance(value, ast.List):
            for elt in value.elts:
                if isinstance(elt, ast.Attribute) and elt.attr == "legacy":
                    return True
    return False


def _collect_py_files(directory: Path) -> list[Path]:
    """Recursively collect .py test files, excluding __init__ and conftest."""
    return sorted(directory.rglob("test_*.py"))


@pytest.mark.parametrize(
    "rel_path",
    [
        "tests/conftest.py",
        "tests/fakes/__init__.py",
    ],
)
def test_target_collection_helpers_have_no_eager_legacy_imports(rel_path: str) -> None:
    """Collection helpers must stay target-safe at import/collection time."""
    helper_path = PROJECT_ROOT / rel_path
    tree = ast.parse(helper_path.read_text(encoding="utf-8"))

    violations: list[str] = []
    for imp in _module_body_runtime_imports(tree):
        for prefix in LEGACY_IMPORT_PREFIXES:
            if imp.startswith(prefix):
                violations.append(f"{imp} from {helper_path.relative_to(PROJECT_ROOT)}")

    assert not violations, "Collection helper eagerly imports legacy modules:\n" + "\n".join(violations)


def test_legacy_architecture_tests_are_marked() -> None:
    """Legacy Plugin/EventBus architecture checks must be filterable."""
    violations: list[str] = []
    for rel_path in sorted(LEGACY_ARCHITECTURE_TESTS):
        test_path = PROJECT_ROOT / rel_path
        tree = ast.parse(test_path.read_text(encoding="utf-8"))
        if not _has_legacy_architecture_mark(tree):
            violations.append(rel_path)

    assert not violations, "Legacy architecture tests missing pytest.mark.legacy_architecture:\n" + "\n".join(
        violations
    )


def test_legacy_deletion_readiness_document_tracks_all_legacy_packages() -> None:
    """The Phase 9 readiness document must list every legacy package explicitly."""
    doc_path = PROJECT_ROOT / "docs" / "migration" / "legacy-deletion-readiness.md"
    assert doc_path.is_file(), "docs/migration/legacy-deletion-readiness.md is required for Phase 9"

    text = doc_path.read_text(encoding="utf-8")
    missing = sorted(package for package in LEGACY_PACKAGES if package not in text)
    assert not missing, "Deletion readiness document does not track legacy packages:\n" + "\n".join(missing)


# -- Phase 9 extended guard tests -----------------------------------------------


def test_target_packages_do_not_import_legacy_packages() -> None:
    """Target v1.2.1 packages must not depend on legacy Plugin/EventBus modules."""
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


def test_legacy_test_files_are_marked() -> None:
    """All test files in legacy directories must have pytestmark = pytest.mark.legacy."""
    violations: list[str] = []
    for test_dir in sorted(LEGACY_TEST_DIRS):
        dir_path = PROJECT_ROOT / test_dir
        if not dir_path.is_dir():
            continue
        for py_file in _collect_py_files(dir_path):
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
            if not _has_legacy_mark(tree):
                violations.append(py_file.relative_to(PROJECT_ROOT).as_posix())
    assert not violations, "Legacy test files missing pytest.mark.legacy:\n" + "\n".join(violations)


def test_fakes_session_has_no_eager_legacy_imports() -> None:
    """tests/fakes/session.py must not eagerly import from legacy packages."""
    session_path = PROJECT_ROOT / "tests" / "fakes" / "session.py"
    tree = ast.parse(session_path.read_text(encoding="utf-8"))
    violations: list[str] = []
    for imp in _module_body_runtime_imports(tree):
        for prefix in LEGACY_IMPORT_PREFIXES:
            if imp.startswith(prefix):
                violations.append(imp)
    assert not violations, "tests/fakes/session.py eagerly imports legacy modules:\n" + "\n".join(violations)


def test_legacy_conftest_exists() -> None:
    """tests/legacy/conftest.py must exist to host legacy-only fixtures."""
    legacy_conftest = PROJECT_ROOT / "tests" / "legacy" / "conftest.py"
    assert legacy_conftest.is_file(), "tests/legacy/conftest.py is required for legacy fixture isolation"


def test_root_conftest_has_no_legacy_type_checking_imports() -> None:
    """Root conftest must not import legacy modules even under TYPE_CHECKING."""
    conftest_path = PROJECT_ROOT / "tests" / "conftest.py"
    tree = ast.parse(conftest_path.read_text(encoding="utf-8"))
    violations: list[str] = []
    for node in tree.body:
        if not _is_type_checking_guard(node):
            continue
        if not isinstance(node, ast.If):
            continue
        for child in node.body:
            if isinstance(child, ast.Import):
                for alias in child.names:
                    for prefix in LEGACY_IMPORT_PREFIXES:
                        if alias.name.startswith(prefix):
                            violations.append(alias.name)
            elif isinstance(child, ast.ImportFrom) and child.module:
                for prefix in LEGACY_IMPORT_PREFIXES:
                    if child.module.startswith(prefix):
                        violations.append(child.module)
    assert not violations, "Root conftest has legacy imports under TYPE_CHECKING:\n" + "\n".join(violations)
