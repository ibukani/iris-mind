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
    dependencies={"EventBus", "Account"},
    provides=["RoomManager", "RoomStore"],
    description="ルーム管理（ルームCRUD・メンバーシップ管理・アカウント連携）",
)


class RoomPlugin(PluginProtocol):
    MANIFEST = MANIFEST

    def init(self, manager: PluginManager) -> None:
        manager.register_manifest(MANIFEST)

        from iris.event.event_bus import EventBus
        from iris.room.handler import _RoomEventHandler
        from iris.room.manager import RoomManager
        from iris.room.store import RoomStore

        cfg = manager.get_plugin_config("room")
        rooms_path = str(cfg.get("rooms_path", ".iris/data/rooms.jsonl"))
        members_path = str(cfg.get("members_path", ".iris/data/room_members.jsonl"))

        store = RoomStore(rooms_path=rooms_path, members_path=members_path)
        event_bus = manager.resolve(EventBus)

        from iris.account.manager import AccountManager as AccountManagerCls

        account_manager = manager.resolve_optional(AccountManagerCls)
        manager_inst = RoomManager(store=store, event_bus=event_bus, account_manager=account_manager)

        self._handler = _RoomEventHandler(
            room_provider=manager_inst,
            account_provider=account_manager,
        )

        manager.provide(RoomStore, store)
        manager.provide(RoomManager, manager_inst)
        manager.provide(_RoomEventHandler, self._handler)

        from iris.room.hooks import register_hooks

        register_hooks(manager)

    def start(self, manager: PluginManager) -> None:
        pass

    def stop(self, manager: PluginManager) -> None:
        pass


plugin: PluginProtocol = RoomPlugin()
