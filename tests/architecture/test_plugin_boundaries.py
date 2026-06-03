"""
Architecture tests — plugin boundary rules.

Every plugin package (except kernel, event, admin) must follow the PluginProtocol contract:
  - Export a MANIFEST instance (PluginManifest)
  - Export a `plugin` instance implementing PluginProtocol
  - Plugin class must have init/start/stop methods
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.legacy_architecture

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# Plugin packages to check (excludes kernel, event, admin which are not plugins)
PLUGIN_PACKAGES: list[str] = [
    "iris/account",
    "iris/agency",
    "iris/heartbeat",
    "iris/io",
    "iris/limbic",
    "iris/llm",
    "iris/memory",
    "iris/room",
    "iris/tools",
]


def _parse_init(init_path: Path) -> ast.Module | None:
    try:
        return ast.parse(init_path.read_text(encoding="utf-8"))
    except (SyntaxError, FileNotFoundError):
        return None


def _has_name(tree: ast.Module, name: str) -> bool:
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return True
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == name:
            return True
    return False


def _has_class_with_methods(tree: ast.Module, class_name: str, methods: list[str]) -> bool:
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            class_methods = {n.name for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
            return all(m in class_methods for m in methods)
    return False


def test_plugin_packages_have_manifest() -> None:
    """Each plugin package must export a MANIFEST instance."""
    missing: list[str] = []
    for pkg in PLUGIN_PACKAGES:
        init_path = PROJECT_ROOT / pkg / "__init__.py"
        tree = _parse_init(init_path)
        if tree is None:
            missing.append(f"{pkg}/__init__.py (not found or unparseable)")
            continue
        if not _has_name(tree, "MANIFEST"):
            missing.append(f"{pkg}/__init__.py (no MANIFEST assignment)")
    assert not missing, "Plugin packages missing MANIFEST:\n" + "\n".join(missing)


def test_plugin_packages_export_plugin_instance() -> None:
    """Each plugin package must export a `plugin` instance."""
    missing: list[str] = []
    for pkg in PLUGIN_PACKAGES:
        init_path = PROJECT_ROOT / pkg / "__init__.py"
        tree = _parse_init(init_path)
        if tree is None:
            missing.append(f"{pkg}/__init__.py (not found or unparseable)")
            continue
        if not _has_name(tree, "plugin"):
            missing.append(f"{pkg}/__init__.py (no 'plugin' assignment)")
    assert not missing, "Plugin packages missing 'plugin' export:\n" + "\n".join(missing)


def test_plugin_classes_implement_protocol() -> None:
    """Each plugin class must implement init, start, stop methods (PluginProtocol)."""
    required_methods = ["init", "start", "stop"]
    violations: list[str] = []
    for pkg in PLUGIN_PACKAGES:
        init_path = PROJECT_ROOT / pkg / "__init__.py"
        tree = _parse_init(init_path)
        if tree is None:
            continue
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.ClassDef) and node.name.endswith("Plugin"):
                class_methods = {n.name for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
                missing_methods = [m for m in required_methods if m not in class_methods]
                if missing_methods:
                    violations.append(f"{pkg}/{node.name} missing methods: {missing_methods}")
    assert not violations, "Plugin classes missing required methods:\n" + "\n".join(violations)
