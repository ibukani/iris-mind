from __future__ import annotations

from collections.abc import Callable
from typing import Any

from loguru import logger

from iris.event.event_bus import EventBus
from iris.event.tracer import EventTracer
from iris.kernel.plugin.hooks import HookRegistry
from iris.kernel.plugin.service_container import ServiceContainer

from .config import Config
from .plugin import (
    KernelState,
    PluginLifecycle,
    PluginManifest,
    discover_plugin_manifests,
)


class PluginManager:
    """Plugin の発見・組み立て・ライフサイクル管理。"""

    def __init__(self, config: Config, debug: bool = False) -> None:
        self._config = config
        self._debug = debug
        self._tracer = EventTracer(max_entries=config.debug.trace_max_entries)
        self._tracer.set_enabled(config.debug.enabled)
        self._event_bus = EventBus(tracer=self._tracer)
        self._hook_registry = HookRegistry()
        self._di = ServiceContainer()
        self._state = KernelState()
        self._lifecycle = PluginLifecycle(builtin_service_types={EventBus})

    # ── Infrastructure accessors ──

    @property
    def config(self) -> Config:
        return self._config

    @property
    def debug(self) -> bool:
        return self._debug

    @property
    def event_bus(self) -> EventBus:
        return self._event_bus

    @property
    def hook_registry(self) -> HookRegistry:
        return self._hook_registry

    @property
    def tracer(self) -> EventTracer:
        return self._tracer

    # ── Plugin lifecycle ──

    def discover_and_build_all(self) -> None:
        self._di.provide(EventBus, self._event_bus)
        self._di.provide(HookRegistry, self._hook_registry)
        self._di.provide(Config, self._config)
        self._di.provide(PluginManager, self)

        manifests = discover_plugin_manifests(self._config.plugins.paths)
        self._lifecycle.load(manifests, self._config.plugins.disabled)
        self._lifecycle.init_all(self)
        self._lifecycle.notify_config_loaded(self)
        self._hook_registry.freeze()
        self._di.freeze()

    def start_all(self) -> None:
        self._lifecycle.start_all(self)
        self._lifecycle.mark_all_ready(self)
        logger.info("PluginManager: all plugins started")

    def stop_all(self) -> None:
        logger.info("PluginManager: stopping")
        self._lifecycle.notify_pre_shutdown(self)
        self._lifecycle.stop_all(self)

    # ── DI ──

    def provide[T](self, key: type[T], instance: T, *, name: str = "default") -> None:
        self._di.provide(key, instance, name=name)

    def resolve[T](self, key: type[T], *, name: str = "default") -> T:
        return self._di.resolve(key, name=name)

    def resolve_optional[T](self, key: type[T], *, name: str = "default") -> T | None:
        return self._di.resolve_optional(key, name=name)

    # ── State ──

    @property
    def global_state(self) -> str:
        return self._state.global_state

    @property
    def layer_states(self) -> dict[str, str]:
        return self._state.layer_states

    def set_layer_state(self, layer: str, state: str) -> None:
        self._state.set_layer_state(layer, state)

    def get_state(self) -> dict[str, Any]:
        base = self._state.get_state()
        base["plugin_count"] = len(self._lifecycle.plugins)
        base["plugin_states"] = {name: p.state.value for name, p in self._lifecycle.plugins.items()}
        return base

    # ── Shutdown ──

    @property
    def shutdown_requested(self) -> bool:
        return self._state.shutdown_requested

    def request_shutdown(self) -> None:
        self._state.request_shutdown()

    # ── Plugin config ──

    def get_plugin_config(self, plugin_name: str) -> dict[str, object]:
        return self._config.plugins.config.get(plugin_name, {})

    def register_manifest(self, manifest: PluginManifest) -> None:
        if manifest.name not in self._lifecycle.plugins:
            from iris.kernel.plugin.lifecycle.models import PluginInstance

            self._lifecycle.plugins[manifest.name] = PluginInstance(manifest=manifest, module=None)

    def reload_plugin(self, plugin_name: str) -> bool:
        return self._lifecycle.reload_plugin(plugin_name, self)

    # ── Hook helpers ──

    def register_hook(self, hook_name: str, handler: Callable[..., Any], priority: int = 500) -> None:
        self._hook_registry.register(hook_name, handler, priority=priority)


__all__ = ["PluginManager"]
