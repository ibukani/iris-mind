from __future__ import annotations

from typing import TYPE_CHECKING

from iris.kernel.plugin import PluginCategory, PluginManifest, PluginPhase, PluginProtocol

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

        from iris.event.event_bus import EventBus
        from iris.room.batcher import RoomJoinBatcher
        from iris.room.dispatcher import _RoomDispatcher
        from iris.room.manager import RoomManager
        from iris.room.store import RoomStore

        store = RoomStore()
        event_bus = manager.resolve(EventBus)

        join_batcher = RoomJoinBatcher(event_bus=event_bus)

        from iris.account.manager import AccountManager as AccountManagerCls

        account_manager = manager.resolve_optional(AccountManagerCls)
        manager_inst = RoomManager(
            store=store,
            event_bus=event_bus,
            account_manager=account_manager,
            join_batcher=join_batcher,
        )

        dispatcher = _RoomDispatcher(room_manager=manager_inst, account_manager=account_manager)

        manager.provide(RoomStore, store)
        manager.provide(RoomJoinBatcher, join_batcher)
        manager.provide(RoomManager, manager_inst)
        manager.provide(_RoomDispatcher, dispatcher)

        from iris.room.handler import _RoomEventHandler

        event_handler = _RoomEventHandler(
            event_bus=event_bus,
            store=store,
            room_manager=manager_inst,
            account_manager=account_manager,
        )
        manager.provide(_RoomEventHandler, event_handler)

        from iris.room.hooks import register_hooks

        register_hooks(manager)

    def start(self, manager: PluginManager) -> None:
        pass

    def stop(self, manager: PluginManager) -> None:
        from iris.room.batcher import RoomJoinBatcher

        # ルーム参加のバッチ処理を停止（インメモリで保存しているため）
        # batcher = manager.resolve_optional(RoomJoinBatcher)
        # if batcher:
        #     batcher.stop()


plugin: PluginProtocol = RoomPlugin()
