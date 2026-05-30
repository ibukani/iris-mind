from __future__ import annotations

from typing import TYPE_CHECKING

from iris.event.event_bus import EventBus
from iris.io.models import (
    AuthMessage,
    AuthResult,
    CommandInput,
    CommandOutput,
    ControlMessage,
    Direction,
    Message,
    Permission,
    PingMessage,
    PongMessage,
    SessionInfo,
    SessionState,
)
from iris.io.session.config import SessionConfig
from iris.io.session.manager import SessionManager
from iris.io.transport.grpc_listener import GrpcListener
from iris.kernel.plugin import PluginCategory, PluginManifest, PluginPhase, PluginProtocol

if TYPE_CHECKING:
    from iris.kernel.manager import PluginManager

MANIFEST = PluginManifest(
    name="io",
    version="0.1.0",
    category=PluginCategory.CORE,
    phase=PluginPhase.CORE,
    dependencies={"EventBus"},
    provides=["IOManager", "SessionManager", "GrpcListener"],
    description="入出力中継層（視床）",
)


class IoPlugin(PluginProtocol):
    MANIFEST = MANIFEST

    def init(self, manager: PluginManager) -> None:
        manager.register_manifest(MANIFEST)
        event_bus = manager.resolve(EventBus)

        session_mgr = SessionManager(
            config=SessionConfig(**manager.config.session.model_dump()),
            event_bus=event_bus,
        )
        grpc_listener = GrpcListener(session_manager=session_mgr)

        from iris.io.gateway import _IOGateway

        gateway = _IOGateway(session_manager=session_mgr, event_bus=event_bus)

        from iris.io.manager import IOManager

        io_mgr = IOManager(
            gateway=gateway,
            session_manager=session_mgr,
            grpc_listener=grpc_listener,
        )

        manager.provide(IOManager, io_mgr)
        manager.provide(SessionManager, session_mgr)
        manager.provide(GrpcListener, grpc_listener)

        from iris.io.handler import _IOEventHandler

        _IOEventHandler(event_bus=event_bus, session_manager=session_mgr)

        from .hooks import register_hooks

        register_hooks(manager)

    def start(self, manager: PluginManager) -> None:
        pass

    def stop(self, manager: PluginManager) -> None:
        from iris.io.manager import IOManager

        io_mgr = manager.resolve(IOManager)
        io_mgr.stop()


plugin: PluginProtocol = IoPlugin()

__all__ = [
    "AuthMessage",
    "AuthResult",
    "CommandInput",
    "CommandOutput",
    "ControlMessage",
    "Direction",
    "GrpcListener",
    "Message",
    "Permission",
    "PingMessage",
    "PongMessage",
    "SessionInfo",
    "SessionManager",
    "SessionState",
]
