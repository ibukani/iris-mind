from __future__ import annotations

from typing import TYPE_CHECKING

from iris.kernel.plugin import PluginCategory, PluginManifest, PluginPhase, PluginProtocol

from .builder import build_room

if TYPE_CHECKING:
    from iris.kernel.manager import PluginManager

MANIFEST = PluginManifest(
    name="room",
    version="0.1.0",
    category=PluginCategory.LAYER,
    phase=PluginPhase.STORE,
    dependencies={"EventBus", "account"},
    provides=["RoomManager", "RoomStore", "RoomJoinBatcher"],
    description="ルーム管理（ルームCRUD・メンバーシップ管理・アカウント連携）",
)


class RoomPlugin(PluginProtocol):
    MANIFEST = MANIFEST

    def init(self, manager: PluginManager) -> None:
        manager.register_manifest(MANIFEST)
        components = build_room(manager)
        from iris.room.batcher import RoomJoinBatcher
        from iris.room.dispatcher import _RoomDispatcher
        from iris.room.handler import _RoomEventHandler
        from iris.room.manager import RoomManager
        from iris.room.store import RoomStore

        manager.provide(RoomStore, components["store"])
        manager.provide(RoomJoinBatcher, components["join_batcher"])
        manager.provide(RoomManager, components["room_manager"])
        manager.provide(_RoomDispatcher, components["dispatcher"])
        manager.provide(_RoomEventHandler, components["event_handler"])

    def start(self, manager: PluginManager) -> None:
        pass

    def stop(self, manager: PluginManager) -> None:
        pass


plugin: PluginProtocol = RoomPlugin()
