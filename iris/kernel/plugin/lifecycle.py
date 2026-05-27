from __future__ import annotations

from graphlib import TopologicalSorter
from types import ModuleType
from typing import TYPE_CHECKING

from loguru import logger

from iris.kernel.plugin.protocol import PluginProtocol

from .manifest import PluginManifest, PluginPhase, PluginState

if TYPE_CHECKING:
    from iris.kernel.manager import PluginManager


class PluginInstance:
    __slots__ = ("manifest", "module", "state")

    def __init__(self, manifest: PluginManifest, module: ModuleType) -> None:
        self.manifest = manifest
        self.module = module
        self.state = PluginState.UNLOADED


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

        self._resolve_order()

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

    def stop_all(self, manager: PluginManager) -> None:
        for name in reversed(self._order):
            p = self._plugins.get(name)
            if p is None or p.state not in (PluginState.STARTED, PluginState.INITIALIZED):
                continue
            try:
                plugin = self._resolve_plugin(p.module)
                plugin.stop(manager)
                p.state = PluginState.STOPPED
                logger.info("PluginLifecycle: stopped '{}'", name)
            except Exception:
                logger.exception("PluginLifecycle: stop failed for '{}'", name)

    # ── Internal ──

    @staticmethod
    def _resolve_plugin(module: ModuleType) -> PluginProtocol:
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

    def _resolve_order(self) -> None:
        graph: dict[str, set[str]] = {name: set(p.manifest.dependencies) for name, p in self._plugins.items()}

        known_services: set[str] = set(self._plugins)
        for p in self._plugins.values():
            known_services.update(p.manifest.provides)
        known_services.update(self._builtin_service_names)

        for dep_set in graph.values():
            for dep in dep_set:
                if dep not in known_services:
                    raise KeyError(f"Plugin has unresolved dependency '{dep}'")

        phases: dict[PluginPhase, list[str]] = {}
        for name, p in self._plugins.items():
            phases.setdefault(p.manifest.phase, []).append(name)

        self._order = []
        for phase in sorted(PluginPhase):
            names = phases.get(phase, [])
            if not names:
                continue
            phase_graph = {n: graph[n] for n in names}
            try:
                ts: TopologicalSorter[str] = TopologicalSorter(phase_graph)
                phase_order = list(ts.static_order())  # type: ignore[arg-type]
            except Exception:
                logger.exception("PluginLifecycle: cycle detected in phase {}", phase.name)
                raise
            for name in phase_order:
                if name in self._plugins:
                    self._order.append(name)

        logger.info(
            "PluginLifecycle: order: {}",
            " → ".join(f"({self._plugins[n].manifest.phase.name}){n}" for n in self._order),
        )

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
