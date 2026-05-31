from __future__ import annotations

import importlib
import sys
from types import ModuleType
from typing import TYPE_CHECKING

from loguru import logger

from iris.kernel.plugin.manifest import PluginManifest, PluginState
from iris.kernel.plugin.protocol import PluginProtocol

from .dependency import DependencyError as DependencyError
from .dependency import resolve_order, verify_dependencies
from .models import PluginInstance

if TYPE_CHECKING:
    from iris.kernel.manager import PluginManager


class PluginLifecycle:
    def __init__(self, builtin_service_types: set[type] | None = None) -> None:
        self._plugins: dict[str, PluginInstance] = {}
        self._order: list[str] = []
        self._builtin_service_names: set[str] = {t.__name__ for t in (builtin_service_types or set())}

    @property
    def plugins(self) -> dict[str, PluginInstance]:
        return self._plugins

    @property
    def order(self) -> list[str]:
        return self._order

    def load(
        self,
        manifests: list[tuple[ModuleType, PluginManifest]],
        disabled: list[str],
    ) -> None:
        for module, manifest in manifests:
            if manifest.name in disabled:
                logger.info("PluginLifecycle: skipping disabled '{}'", manifest.name)
                continue
            self._plugins[manifest.name] = PluginInstance(manifest=manifest, module=module)

        self._order = resolve_order(self._plugins, self._builtin_service_names)
        verify_dependencies(self._plugins, self._builtin_service_names)

    # ── Lifecycle phases ──

    def init_all(self, manager: PluginManager) -> None:
        for name in self._order:
            p = self._plugins[name]
            try:
                plugin = self._resolve_plugin(p.module)
                plugin.init(manager)
                p.state = PluginState.INITIALIZED
                logger.info("PluginLifecycle: initialized '{}' (v{})", name, p.manifest.version)
            except Exception:
                logger.exception("PluginLifecycle: init failed for '{}'", name)
                p.state = PluginState.ERROR
                raise

    def notify_config_loaded(self, manager: PluginManager) -> None:
        for name in self._order:
            p = self._plugins[name]
            if p.state != PluginState.INITIALIZED:
                continue
            try:
                plugin = self._resolve_plugin(p.module)
                plugin.on_config_loaded(manager)
            except Exception:
                logger.exception("PluginLifecycle: on_config_loaded failed for '{}'", name)

    def start_all(self, manager: PluginManager) -> None:
        for name in self._order:
            p = self._plugins[name]
            if p.state == PluginState.ERROR:
                continue
            try:
                plugin = self._resolve_plugin(p.module)
                plugin.start(manager)
                p.state = PluginState.STARTED
                logger.info("PluginLifecycle: started '{}'", name)
            except Exception:
                logger.exception("PluginLifecycle: start failed for '{}'", name)
                p.state = PluginState.ERROR
                self._stop_started_before(name, manager)
                raise

    def mark_all_ready(self, manager: PluginManager | None = None) -> None:
        for name in self._order:
            p = self._plugins[name]
            if p.state == PluginState.STARTED:
                p.state = PluginState.READY
                logger.info("PluginLifecycle: '{}' marked as READY", name)
        if manager is not None:
            self._notify_all_ready(manager)

    def _notify_all_ready(self, manager: PluginManager) -> None:
        for name in self._order:
            p = self._plugins[name]
            if p.state not in (PluginState.READY, PluginState.STARTED):
                continue
            try:
                plugin = self._resolve_plugin(p.module)
                plugin.on_all_ready(manager)
            except Exception:
                logger.exception("PluginLifecycle: on_all_ready failed for '{}'", name)

    def notify_pre_shutdown(self, manager: PluginManager) -> None:
        for name in reversed(self._order):
            p = self._plugins.get(name)
            if p is None or p.state not in (PluginState.STARTED, PluginState.READY, PluginState.INITIALIZED):
                continue
            try:
                plugin = self._resolve_plugin(p.module)
                plugin.on_pre_shutdown(manager)
            except Exception:
                logger.exception("PluginLifecycle: on_pre_shutdown failed for '{}'", name)

    def stop_all(self, manager: PluginManager) -> None:
        for name in reversed(self._order):
            p = self._plugins.get(name)
            if p is None or p.state not in (PluginState.STARTED, PluginState.READY, PluginState.INITIALIZED):
                continue
            try:
                plugin = self._resolve_plugin(p.module)
                p.state = PluginState.STOPPING
                plugin.stop(manager)
                p.state = PluginState.STOPPED
                logger.info("PluginLifecycle: stopped '{}'", name)
            except Exception:
                logger.exception("PluginLifecycle: stop failed for '{}'", name)

    def reload_plugin(self, plugin_name: str, manager: PluginManager) -> bool:
        if plugin_name not in self._plugins:
            logger.warning("PluginLifecycle: plugin '{}' not found for reload", plugin_name)
            return False

        p = self._plugins[plugin_name]
        if p.state not in (PluginState.STARTED, PluginState.READY):
            logger.warning("PluginLifecycle: plugin '{}' is not running (state={})", plugin_name, p.state.value)
            return False

        # Step 1: Stop
        try:
            plugin = self._resolve_plugin(p.module)
            p.state = PluginState.STOPPING
            plugin.stop(manager)
            p.state = PluginState.STOPPED
            logger.info("PluginLifecycle: '{}' stopped for reload", plugin_name)
        except Exception:
            logger.exception("PluginLifecycle: stop failed for '{}' during reload", plugin_name)
            p.state = PluginState.ERROR
            return False

        # Step 2: Reload module
        try:
            assert p.module is not None
            module_name = p.module.__name__
            if module_name in sys.modules:
                new_module = importlib.reload(p.module)
            else:
                new_module = importlib.import_module(module_name)
            p.module = new_module
            logger.info("PluginLifecycle: '{}' module reloaded", plugin_name)
        except Exception:
            logger.exception("PluginLifecycle: module reload failed for '{}'", plugin_name)
            p.state = PluginState.ERROR
            return False

        # Step 3: Re-init and start
        try:
            new_plugin = self._resolve_plugin(new_module)
            new_plugin.init(manager)
            p.state = PluginState.INITIALIZED
            new_plugin.start(manager)
            p.state = PluginState.STARTED
            logger.info("PluginLifecycle: '{}' reloaded successfully", plugin_name)
            return True
        except Exception:
            logger.exception("PluginLifecycle: re-init/start failed for '{}'", plugin_name)
            p.state = PluginState.ERROR
            return False

    # ── Internal ──

    @staticmethod
    def _resolve_plugin(module: ModuleType | None) -> PluginProtocol:
        if module is None:
            raise RuntimeError("Plugin module is None")
        plugin: object | None = getattr(module, "plugin", None)
        if isinstance(plugin, PluginProtocol):
            return plugin

        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if isinstance(attr, type) and issubclass(attr, PluginProtocol) and hasattr(attr, "MANIFEST"):
                return attr()

        if isinstance(module, PluginProtocol):
            return module

        raise RuntimeError(f"Module '{module.__name__}' has no PluginProtocol implementation")

    def _stop_started_before(self, failed_name: str, manager: PluginManager) -> None:
        idx = self._order.index(failed_name) if failed_name in self._order else -1
        for name in reversed(self._order[:idx]):
            p = self._plugins.get(name)
            if p is None or p.state != PluginState.STARTED:
                continue
            try:
                plugin = self._resolve_plugin(p.module)
                plugin.stop(manager)
                p.state = PluginState.STOPPED
            except Exception:
                logger.exception("PluginLifecycle: cleanup stop failed for '{}'", name)
