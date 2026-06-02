"""Kernel のコンポーネント組み立て (DI 配線)。

`PluginManager` は `__init__` 時に全サービスを `provide` する責務を持つが、
plugin 間の接続 (例えば `RoomManager` が `AccountManager` を必要とする場合)
は **明示的な builder 関数** で解決する。PluginManager は service locator
として使わず、組み立て済みコンポーネントを受け取るだけにする。

フロー:
1. `build_kernel(config)` が `KernelComponents` を返す。
2. KernelComponents は PluginManager / CommandHandler / SystemDiagnostics / KernelProcess を保持。
3. KernelProcess は `start()` で `io_manager.start()` を呼び、その後 `manager.start_all()`。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from iris.kernel.commands.handler import CommandHandler
    from iris.kernel.config import Config
    from iris.kernel.diagnostics import SystemDiagnostics
    from iris.kernel.manager import PluginManager
    from iris.kernel.process import KernelProcess


@dataclass(frozen=True)
class _KernelComponentsInternal:
    manager: PluginManager
    diagnostics: SystemDiagnostics
    cmd_handler: CommandHandler
    process: KernelProcess


@dataclass(frozen=True)
class KernelComponents:
    """Kernel 起動に必要なコンポーネント群。"""

    manager: PluginManager
    diagnostics: SystemDiagnostics
    cmd_handler: CommandHandler
    process: KernelProcess
    shutdown_fn: Callable[[], None]


def build_kernel(config: Config, debug: bool = False) -> KernelComponents:
    """Kernel を組み立てる。manager を起動し、必要な component を返す。

    Args:
        config: 起動設定。
        debug: True でデバッグモード。
    """
    from iris.kernel.diagnostics import SystemDiagnostics
    from iris.kernel.manager import PluginManager
    from iris.kernel.process import KernelProcess

    manager = PluginManager(config, debug=debug)
    manager.discover_and_build_all()

    diagnostics = SystemDiagnostics(
        event_bus=manager.event_bus,
        tracer=manager.tracer,
        kernel=manager,
    )
    _attach_layer_state_provider(diagnostics, manager)

    cmd_handler = _build_command_handler(manager, config, diagnostics)
    manager.provide(type(cmd_handler), cmd_handler)

    process = KernelProcess(config, debug=debug)
    process.attach_components(_KernelComponentsInternal(manager, diagnostics, cmd_handler, process))

    def _shutdown() -> None:
        manager.request_shutdown()

    return KernelComponents(
        manager=manager,
        diagnostics=diagnostics,
        cmd_handler=cmd_handler,
        process=process,
        shutdown_fn=_shutdown,
    )


def _attach_layer_state_provider(diagnostics: SystemDiagnostics, manager: PluginManager) -> None:
    """各 plugin が DI に登録した StateProvider を取り出し、diagnostics に接続する。"""
    from iris.agency.manager import AgencyManager
    from iris.io.manager import IOManager
    from iris.memory.manager import MemoryManager

    state_providers: dict[str, object] = {
        "io": manager.resolve_optional(IOManager),
        "memory": manager.resolve_optional(MemoryManager),
        "agency": manager.resolve_optional(AgencyManager),
    }
    diagnostics.attach_layer_providers(state_providers)


def _build_command_handler(manager: PluginManager, config: Config, diagnostics: SystemDiagnostics) -> CommandHandler:
    from iris.io.session.manager import SessionManager
    from iris.kernel.commands.handler import CommandHandler
    from iris.kernel.debug_capture import DebugCapture
    from iris.llm.bridge import LLMBridge
    from iris.memory.manager import MemoryManager
    from iris.tools.registry import ToolRegistry

    def _on_shutdown() -> None:
        manager.request_shutdown()

    return CommandHandler(
        config=config,
        on_shutdown=_on_shutdown,
        on_compact=None,
        memory=manager.resolve_optional(MemoryManager),
        session_mgr=manager.resolve_optional(SessionManager),
        llm=manager.resolve_optional(LLMBridge),
        registry=manager.resolve_optional(ToolRegistry),
        debug_capture=manager.resolve_optional(DebugCapture),
        diagnostics=diagnostics,
    )


def start_kernel_io(components: KernelComponents) -> None:
    """IOManager を起動する。manager.start_all の前段。"""
    from iris.io.manager import IOManager

    io_mgr: IOManager | None = components.manager.resolve_optional(IOManager)
    if io_mgr is None:
        logger.warning("KernelFactory: IOManager not registered, skipping IO start")
        return
    host = components.process.config_host
    port = components.process.config_port
    io_mgr.start(host=host, port=port)


__all__ = ["KernelComponents", "build_kernel", "start_kernel_io"]
