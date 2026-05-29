from __future__ import annotations

from typing import Any

from loguru import logger

from iris.event.event_bus import EventBus
from iris.event.tracer import EventTracer

from .config import Config
from .plugin import (
    HookRegistry,
    KernelState,
    PluginLifecycle,
    PluginManifest,
    ServiceContainer,
    discover_plugin_manifests,
)


class PluginManager:
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
        self._cmd_handler: Any = None
        self._diagnostics: Any = None

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
        self._init_builtin()
        self._wire_cross_layer_dependencies()

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
            from .plugin.lifecycle import PluginInstance

            self._lifecycle.plugins[manifest.name] = PluginInstance(manifest=manifest, module=None)  # type: ignore[arg-type]

    def reload_plugin(self, plugin_name: str) -> bool:
        return self._lifecycle.reload_plugin(plugin_name, self)

    # ── Built-in ──

    @property
    def cmd_handler(self) -> Any:
        return self._cmd_handler

    @property
    def diagnostics(self) -> Any:
        return self._diagnostics

    # ── Internal ──

    def _init_builtin(self) -> None:
        self._create_diagnostics()
        self._create_command_handler()

    def _create_diagnostics(self) -> None:
        from iris.agency.manager import AgencyManager
        from iris.io.manager import IOManager
        from iris.kernel.diagnostics import SystemDiagnostics
        from iris.memory.manager import MemoryManager

        self._diagnostics = SystemDiagnostics(
            event_bus=self._event_bus,
            tracer=self._tracer,
            kernel=self,
            io=self._di.resolve_optional(IOManager),
            memory=self._di.resolve_optional(MemoryManager),
            agency=self._di.resolve_optional(AgencyManager),
        )

    def _create_command_handler(self) -> None:
        from iris.agency.manager import AgencyManager
        from iris.io.manager import IOManager
        from iris.io.session.manager import SessionManager
        from iris.kernel.commands.handler import CommandHandler
        from iris.kernel.debug_capture import DebugCapture
        from iris.llm.bridge import LLMBridge
        from iris.memory.manager import MemoryManager
        from iris.memory.user_store import UserStore
        from iris.tools.registry import ToolRegistry

        agency = self._di.resolve_optional(AgencyManager)

        def _on_shutdown() -> None:
            self._state.request_shutdown()

        def _default_compact() -> str:
            return "Compact not available"

        on_compact = (
            agency.compact_context if agency is not None and hasattr(agency, "compact_context") else _default_compact
        )

        self._cmd_handler = CommandHandler(
            config=self._config,
            on_shutdown=_on_shutdown,
            on_compact=on_compact,
            memory=self._di.resolve_optional(MemoryManager),
            session_mgr=self._di.resolve_optional(SessionManager),
            llm=self._di.resolve_optional(LLMBridge),
            registry=self._di.resolve_optional(ToolRegistry),
            debug_capture=self._di.resolve_optional(DebugCapture),
            diagnostics=self._diagnostics,
            user_store=self._di.resolve_optional(UserStore),
        )

        io_mgr = self._di.resolve_optional(IOManager)
        if io_mgr is not None:
            io_mgr.set_command_handler(self._cmd_handler.handle)

    def _wire_cross_layer_dependencies(self) -> None:
        """Plugin間の依存関係をkernelで配線する。

        system メッセージは IO 層（Gateway）→ memory 層（Handler）への
        直接コールバックで接続する（同期レスポンスが必要なため）。
        通常メッセージは EventBus 経由で接続する（Gateway → InputReady → Handler）。
        """
        from iris.io.manager import IOManager
        from iris.memory.handler import _MemoryEventHandler

        io_mgr = self._di.resolve_optional(IOManager)
        handler = self._di.resolve_optional(_MemoryEventHandler)
        if io_mgr is not None and handler is not None:
            io_mgr.set_system_handler(handler.handle_system_message)
