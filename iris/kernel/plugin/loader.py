from __future__ import annotations

import importlib
from pathlib import Path
import sys
from types import ModuleType
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from iris.kernel.plugin.manifest import PluginManifest


def discover_plugin_manifests(paths: list[str]) -> list[tuple[ModuleType, PluginManifest]]:
    results: list[tuple[ModuleType, PluginManifest]] = []
    for base_path in paths:
        p = Path(base_path).expanduser().resolve()
        if not p.is_dir():
            logger.warning("Plugin path not found: {}", p)
            continue
        for candidate in sorted(p.iterdir()):
            if candidate.name.startswith("_") or candidate.name == "kernel" or candidate.name == "event":
                continue
            if not candidate.is_dir():
                continue
            init_file = candidate / "__init__.py"
            if not init_file.exists():
                continue
            module_path = str(init_file.relative_to(Path.cwd()).with_suffix("")).replace("/", ".").replace("\\", ".")
            try:
                module = importlib.import_module(module_path)
            except Exception:
                logger.warning("Failed to import module '{}':", module_path, exc_info=True)
                continue

            manifest = getattr(module, "MANIFEST", None)
            if manifest is None:
                continue

            from iris.kernel.plugin.manifest import PluginManifest

            if not isinstance(manifest, PluginManifest):
                logger.warning("Module '{}' has MANIFEST but it is not a PluginManifest instance", module_path)
                continue

            results.append((module, manifest))

    return results


def discover_sub_plugins(parent_path: str) -> list[ModuleType]:
    modules: list[ModuleType] = []
    p = Path(parent_path)
    if not p.is_dir():
        return modules
    if p not in Path.cwd().iterdir() and not parent_path.startswith(str(Path.cwd())):
        p = Path.cwd() / parent_path

    if not p.is_dir():
        return modules

    for candidate in sorted(p.iterdir()):
        if candidate.suffix != ".py":
            continue
        if candidate.name.startswith("_"):
            continue

        module_path = str(candidate.relative_to(Path.cwd()).with_suffix("")).replace("/", ".").replace("\\", ".")

        try:
            module = sys.modules[module_path] if module_path in sys.modules else importlib.import_module(module_path)
            if module is not None:
                modules.append(module)
        except Exception:
            logger.warning("Failed to import sub-plugin '{}':", module_path, exc_info=True)

    return modules
