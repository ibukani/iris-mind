from __future__ import annotations

from typing import TYPE_CHECKING, Any

from iris.kernel.plugin import PluginCategory, PluginManifest, PluginPhase, PluginProtocol
from iris.kernel.plugin.hooks import hook

if TYPE_CHECKING:
    from iris.kernel.manager import PluginManager

MANIFEST = PluginManifest(
    name="room",
    version="0.1.0",
    category=PluginCategory.LAYER,
    phase=PluginPhase.STORE,
    dependencies={"EventBus", "Account"},
    provides=["RoomProvider", "RoomStore"],
    description="ルーム管理（ルームCRUD・メンバーシップ管理・アカウント連携）",
)


class RoomPlugin(PluginProtocol):
    MANIFEST = MANIFEST

    def init(self, manager: PluginManager) -> None:
        manager.register_manifest(MANIFEST)

        from iris.event.event_bus import EventBus
        from iris.room.handler import _RoomEventHandler
        from iris.room.provider import RoomProvider
        from iris.room.store import RoomStore

        cfg = manager.get_plugin_config("room")
        rooms_path = str(cfg.get("rooms_path", ".iris/data/rooms.jsonl"))
        members_path = str(cfg.get("members_path", ".iris/data/room_members.jsonl"))

        store = RoomStore(rooms_path=rooms_path, members_path=members_path)
        event_bus = manager.resolve(EventBus)

        from iris.account.provider import AccountProvider as AccountProviderCls

        account_provider = manager.resolve_optional(AccountProviderCls)
        provider = RoomProvider(store=store, event_bus=event_bus, account_provider=account_provider)

        self._handler = _RoomEventHandler(
            room_provider=provider,
            account_provider=account_provider,
        )

        manager.provide(RoomStore, store)
        manager.provide(RoomProvider, provider)
        manager.provide(_RoomEventHandler, self._handler)

        manager.hook_registry.register_decorated(self)

        from iris.room.hooks import register_hooks

        register_hooks(manager)

    @hook("io.dispatch", priority=200)
    def _on_dispatch(self, ctx: dict[str, Any]) -> dict[str, Any]:
        msg = ctx["msg"]
        if ctx["type"] == "control" and msg.action.startswith("room."):
            ctx["response"] = self._handler.handle_control_message(msg, ctx["session_id"])
        return ctx

    def start(self, manager: PluginManager) -> None:
        pass

    def stop(self, manager: PluginManager) -> None:
        pass


plugin: PluginProtocol = RoomPlugin()
