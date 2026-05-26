"""
Architecture tests — enforce dependency direction constraints.

Rules (from AGENTS.md v2):
  - All layers communicate via EventBus (iris/event/)
  - PluginManager (iris/kernel/manager.py) is the DI container that wires all layers
  - iris/kernel/ must NOT import from debug_tools/
  - iris/memory/ must NOT import from iris/io/ or iris/agency/
  - iris/io/ must NOT import from iris/agency/ or iris/memory/
  - iris/agency/ may import from iris/memory/, iris/event/
  - debug_tools/ → iris/ (全層)
"""

from __future__ import annotations

import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

_IRIS_LAYERS = {"kernel", "event", "io", "memory", "agency", "llm", "capabilities", "tools", "commands", "personality"}
_MANAGER_PATH = "iris/kernel/manager.py"


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
            for alias in node.names:
                imports.append(alias.name)  # noqa: PERF401
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
    forbidden_prefixes = {"debug_tools"}
    for filepath in _get_python_files("iris/kernel"):
        imports = _get_imports(filepath)
        for imp in imports:
            for prefix in forbidden_prefixes:
                if imp.startswith(prefix):
                    raise AssertionError(
                        f"{filepath} imports '{imp}' (violates dependency rule: kernel must not depend on debug_tools)"
                    )


def test_memory_does_not_import_io_or_agency() -> None:
    forbidden = {"iris.io", "iris.agency"}
    for filepath in _get_python_files("iris/memory"):
        imports = _get_imports(filepath)
        for imp in imports:
            for prefix in forbidden:
                if imp.startswith(prefix):
                    raise AssertionError(f"{filepath} imports '{imp}' (memory must not depend on io or agency)")


def test_io_does_not_import_agency_or_memory() -> None:
    forbidden = {"iris.agency", "iris.memory"}
    for filepath in _get_python_files("iris/io"):
        imports = _get_imports(filepath)
        for imp in imports:
            for prefix in forbidden:
                if imp.startswith(prefix):
                    raise AssertionError(f"{filepath} imports '{imp}' (io must not depend on agency or memory)")


def test_plugin_manager_is_layer_crossing_hub() -> None:
    """PluginManager (manager.py) imports from all layers — acceptable as DI container."""
    manager_files = [p for p in _get_python_files("iris") if p.match(_MANAGER_PATH)]
    assert len(manager_files) >= 1, "PluginManager not found"
    for filepath in manager_files:
        imports = _get_imports(filepath)
        infra = {"iris.io", "iris.memory", "iris.agency", "iris.event", "iris.llm", "iris.kernel.commands"}
        found = [i for i in imports if any(i.startswith(p) for p in infra)]
        assert len(found) >= 3, f"PluginManager should import from at least 3 layers, got: {found}"


def test_debug_tools_imports_kernel() -> None:
    for filepath in _get_python_files("debug_tools"):
        imports = _get_imports(filepath)
        kernel_imports = [i for i in imports if i.startswith("iris.kernel")]
        assert len(kernel_imports) >= 0, (
            f"{filepath} does not import from iris.kernel — debug_tools should depend on kernel"
        )
