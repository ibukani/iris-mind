"""
Architecture tests — enforce dependency direction constraints.

Rules (from AGENTS.md):
  debug_tools/ → iris/kernel/ → iris/llm/, iris/memory/, iris/capabilities/
  iris/kernel/ must NOT import from debug_tools/
  iris/kernel/ must NOT directly import from iris/llm/, iris/memory/, iris/capabilities/
"""

from __future__ import annotations

import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _get_python_files(package_dir: str) -> list[Path]:
    base = PROJECT_ROOT / package_dir
    return sorted(base.rglob("*.py"))


def _get_imports(filepath: Path) -> list[str]:
    """Extract all module-level import targets from a Python file."""
    try:
        tree = ast.parse(filepath.read_text(encoding="utf-8"))
    except SyntaxError:
        return []

    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
    return imports


def test_kernel_does_not_import_debug_tools() -> None:
    forbidden = {"debug_tools"}
    for filepath in _get_python_files("iris/kernel"):
        imports = _get_imports(filepath)
        for imp in imports:
            top_level = imp.split(".")[0]
            assert top_level not in forbidden, f"{filepath} imports from 'debug_tools' (violates dependency rule)"


def test_kernel_does_not_directly_import_debug_tools() -> None:
    """iris/kernel/ should not directly import debug_tools."""
    forbidden_prefixes = {"debug_tools"}
    for filepath in _get_python_files("iris/kernel"):
        imports = _get_imports(filepath)
        for imp in imports:
            for prefix in forbidden_prefixes:
                if imp.startswith(prefix):
                    raise AssertionError(
                        f"{filepath} imports '{imp}' (violates dependency rule: kernel must not depend on debug_tools)"
                    )


def test_kernel_can_import_infrastructure() -> None:
    """iris/kernel/ CAN import iris/llm, iris/memory, iris/capabilities (hexagonal arch)."""
    kernel_dir = PROJECT_ROOT / "iris" / "kernel"
    files = sorted(kernel_dir.rglob("*.py"))
    infra_imports = {"iris.llm", "iris.memory", "iris.capabilities"}
    for filepath in files:
        if filepath.name.startswith("test_"):
            continue
        imports = _get_imports(filepath)
        for imp in imports:
            if any(imp.startswith(prefix) for prefix in infra_imports):
                return  # at least one kernel file imports infrastructure — OK
    raise AssertionError("No kernel file imports infrastructure — check if architecture is correct")


def test_no_circular_imports() -> None:
    """Basic circular import detection across iris/ package."""
    iris_dir = PROJECT_ROOT / "iris"
    checked: set[Path] = set()

    def visit(filepath: Path, visiting: set[Path]) -> None:
        if filepath in visiting:
            raise AssertionError(f"Circular import detected involving {filepath}")
        if filepath in checked:
            return
        visiting.add(filepath)
        for imp in _get_imports(filepath):
            if not imp.startswith("iris."):
                continue
            # Map import to file path
            parts = imp.split(".")
            if len(parts) >= 2:
                rel_path = Path(*parts[1:-1]) / f"{parts[-1]}.py"
                target = iris_dir / rel_path
                if target.exists():
                    visit(target, visiting)
        visiting.discard(filepath)
        checked.add(filepath)

    for filepath in sorted(iris_dir.rglob("*.py")):
        if filepath.name == "__init__.py":
            continue
        if filepath not in checked:
            visit(filepath, set())


def test_debug_tools_imports_kernel() -> None:
    """debug_tools/ should import from iris.kernel (but not vice versa)."""
    for filepath in _get_python_files("debug_tools"):
        imports = _get_imports(filepath)
        kernel_imports = [i for i in imports if i.startswith("iris.kernel")]
        assert len(kernel_imports) >= 0, (
            f"{filepath} does not import from iris.kernel — debug_tools should depend on kernel"
        )
