"""Legacy migration audit tests.

Lightweight, deterministic scans that detect remaining legacy references in
target packages and test infrastructure.  These tests complement the
migration-control guards by providing broader audit coverage.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.migration

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

LEGACY_IMPORT_PREFIXES: tuple[str, ...] = (
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
)

TARGET_PACKAGES: tuple[str, ...] = (
    "iris/core",
    "iris/contracts",
    "iris/cognitive",
    "iris/presentation",
    "iris/safety",
    "iris/features",
    "iris/adapters",
    "iris/runtime",
)

LEGACY_TEST_DIRS: tuple[str, ...] = (
    "tests/agency",
    "tests/kernel",
    "tests/room",
    "tests/llm",
    "tests/memory",
    "tests/limbic",
    "tests/account",
    "tests/tools",
)


def _runtime_imports(tree: ast.Module) -> list[str]:
    """Extract module-level runtime imports (skip TYPE_CHECKING blocks)."""
    imports: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.If):
            test = node.test
            if isinstance(test, ast.Name) and test.id == "TYPE_CHECKING":
                continue
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
    return imports


def _is_legacy_import(imp: str) -> bool:
    return any(imp.startswith(prefix) for prefix in LEGACY_IMPORT_PREFIXES)


class TestTargetPackageIsolation:
    """Verify target packages have no legacy imports."""

    @pytest.mark.parametrize("pkg_dir", TARGET_PACKAGES)
    def test_no_legacy_imports_in_target_source(self, pkg_dir: str) -> None:
        pkg_path = PROJECT_ROOT / pkg_dir
        if not pkg_path.is_dir():
            pytest.skip(f"{pkg_dir} does not exist")
        violations: list[str] = []
        for py_file in sorted(pkg_path.rglob("*.py")):
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
            for imp in _runtime_imports(tree):
                if _is_legacy_import(imp):
                    violations.append(f"{imp} from {py_file.relative_to(PROJECT_ROOT)}")
        assert not violations, f"Legacy imports found in {pkg_dir}:\n" + "\n".join(violations)


class TestLegacyMarkerCoverage:
    """Verify all legacy test files have the legacy marker."""

    def _has_legacy_mark(self, tree: ast.Module) -> bool:
        for node in tree.body:
            if not isinstance(node, ast.Assign):
                continue
            if not any(isinstance(t, ast.Name) and t.id == "pytestmark" for t in node.targets):
                continue
            value = node.value
            if isinstance(value, ast.Attribute) and value.attr == "legacy":
                return True
            if isinstance(value, ast.List):
                for elt in value.elts:
                    if isinstance(elt, ast.Attribute) and elt.attr == "legacy":
                        return True
        return False

    @pytest.mark.parametrize("test_dir", LEGACY_TEST_DIRS)
    def test_legacy_tests_have_marker(self, test_dir: str) -> None:
        dir_path = PROJECT_ROOT / test_dir
        if not dir_path.is_dir():
            pytest.skip(f"{test_dir} does not exist")
        unmarked: list[str] = []
        for py_file in sorted(dir_path.rglob("test_*.py")):
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
            if not self._has_legacy_mark(tree):
                unmarked.append(py_file.relative_to(PROJECT_ROOT).as_posix())
        assert not unmarked, "Legacy test files without pytest.mark.legacy:\n" + "\n".join(unmarked)


class TestCollectionHelperSafety:
    """Verify test collection helpers stay free of eager legacy imports."""

    @pytest.mark.parametrize(
        "rel_path",
        [
            "tests/conftest.py",
            "tests/fakes/__init__.py",
            "tests/fakes/session.py",
        ],
    )
    def test_no_eager_legacy_imports(self, rel_path: str) -> None:
        file_path = PROJECT_ROOT / rel_path
        if not file_path.is_file():
            pytest.skip(f"{rel_path} does not exist")
        tree = ast.parse(file_path.read_text(encoding="utf-8"))
        violations: list[str] = []
        for imp in _runtime_imports(tree):
            if _is_legacy_import(imp):
                violations.append(imp)
        assert not violations, f"{rel_path} eagerly imports legacy modules:\n" + "\n".join(violations)


class TestLegacyConftestIsolation:
    """Verify legacy fixtures are isolated from root conftest."""

    def test_legacy_conftest_exists(self) -> None:
        legacy_conftest = PROJECT_ROOT / "tests" / "legacy" / "conftest.py"
        assert legacy_conftest.is_file(), "tests/legacy/conftest.py must exist for legacy fixture isolation"

    def test_root_conftest_has_no_legacy_type_checking(self) -> None:
        conftest_path = PROJECT_ROOT / "tests" / "conftest.py"
        tree = ast.parse(conftest_path.read_text(encoding="utf-8"))
        violations: list[str] = []
        for node in tree.body:
            if not isinstance(node, ast.If):
                continue
            test = node.test
            if not (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING"):
                continue
            for child in node.body:
                if isinstance(child, ast.Import):
                    for alias in child.names:
                        if _is_legacy_import(alias.name):
                            violations.append(alias.name)
                elif isinstance(child, ast.ImportFrom) and child.module and _is_legacy_import(child.module):
                    violations.append(child.module)
        assert not violations, "Root conftest has legacy TYPE_CHECKING imports:\n" + "\n".join(violations)


class TestDeletionReadinessDoc:
    """Verify deletion readiness documentation tracks all legacy packages."""

    def test_document_exists(self) -> None:
        doc = PROJECT_ROOT / "docs" / "migration" / "legacy-deletion-readiness.md"
        assert doc.is_file(), "docs/migration/legacy-deletion-readiness.md must exist"

    def test_tracks_all_legacy_packages(self) -> None:
        doc = PROJECT_ROOT / "docs" / "migration" / "legacy-deletion-readiness.md"
        text = doc.read_text(encoding="utf-8")
        legacy_packages = (
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
        )
        missing = [pkg for pkg in legacy_packages if pkg not in text]
        assert not missing, "Deletion readiness doc missing packages:\n" + "\n".join(missing)
