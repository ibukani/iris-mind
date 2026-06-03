"""PluginManager の service locator 化を検出し、禁止するアーキテクチャテスト。

ロジッククラス (manager.py / orchestrator.py / gateway.py / *_manager.py) は
`PluginManager` を保持してはならない。PluginManager への依存は
`__init__.py` または `builder.py` のみが許可される。
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.legacy_architecture

ROOT = Path(__file__).resolve().parents[2] / "iris"

ALLOWED_PLUGINS_WITH_MANAGER = {"__init__.py", "builder.py"}
ALLOWED_DIRS = {"kernel"}


def _iter_python_files(base: Path) -> list[Path]:
    return [p for p in base.rglob("*.py") if p.is_file()]


def _imports_plugin_manager(path: Path) -> bool:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if (node.module or "").endswith("kernel.manager") and node.module.startswith("iris"):
                return True
            for alias in node.names:
                if alias.name == "PluginManager":
                    return True
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if "kernel.manager" in alias.name:
                    return True
    return False


def test_no_service_locator_in_logic_classes() -> None:
    violations: list[str] = []
    for path in _iter_python_files(ROOT):
        rel = path.relative_to(ROOT)
        parts = rel.parts
        if not parts:
            continue
        plugin = parts[0]
        if plugin not in ALLOWED_DIRS and not any(
            p in {"manager", "orchestrator", "gateway", "dispatcher"} for p in parts
        ):
            continue
        if parts[-1] in ALLOWED_PLUGINS_WITH_MANAGER:
            continue
        if plugin in ALLOWED_DIRS and parts[-1] != "manager.py":
            continue
        if _imports_plugin_manager(path):
            violations.append(str(rel))
    assert not violations, (
        f"PluginManager should not be imported in logic classes. Use constructor injection. Violations: {violations}"
    )
