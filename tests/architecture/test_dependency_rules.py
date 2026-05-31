"""
Architecture tests — foundational dependency invariants.

Rules:
  - iris.event is the foundation layer with zero external iris.* dependencies
  - iris.kernel does not depend on debug_tools
  - iris top-level __init__.py only re-exports from event and kernel.config
"""

from __future__ import annotations

import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


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


def test_event_has_no_iris_dependencies() -> None:
    """iris.event is the foundation — must not import from any other iris.* package.

    Self-references within iris.event (e.g. iris.event.event_bus) are allowed.
    Exception: event_types.py is a backward-compatibility shim that re-exports
    domain events from their new locations.
    """
    for filepath in _get_python_files("iris/event"):
        if filepath.name == "event_types.py":
            continue
        imports = _get_imports(filepath)
        iris_imports = [i for i in imports if i.startswith("iris.") and not i.startswith("iris.event")]
        assert not iris_imports, (
            f"{filepath.relative_to(PROJECT_ROOT)} imports from {iris_imports} "
            "— event must have zero external iris.* dependencies"
        )


def test_kernel_does_not_import_debug_tools() -> None:
    """iris.kernel must not depend on debug_tools (debug_tools → iris is allowed)."""
    for filepath in _get_python_files("iris/kernel"):
        imports = _get_imports(filepath)
        for imp in imports:
            top_level = imp.split(".")[0]
            assert top_level != "debug_tools", (
                f"{filepath.relative_to(PROJECT_ROOT)} imports '{imp}' — kernel must not depend on debug_tools"
            )


def test_iris_top_level_only_imports_from_event_and_kernel_config() -> None:
    """iris/__init__.py should only re-export from event and kernel.config."""
    init_file = PROJECT_ROOT / "iris" / "__init__.py"
    tree = ast.parse(init_file.read_text(encoding="utf-8"))
    allowed_prefixes = {"iris.event", "iris.kernel.config"}
    violations = [
        node.module
        for node in ast.walk(tree)
        if (
            isinstance(node, ast.ImportFrom)
            and node.module
            and node.module.startswith("iris.")
            and not any(node.module.startswith(p) for p in allowed_prefixes)
        )
    ]
    assert not violations, (
        f"iris/__init__.py imports from {violations} — top-level should only re-export from event and kernel.config"
    )
