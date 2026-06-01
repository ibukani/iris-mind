"""room Plugin のコンポーネント組み立て。"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from iris.account.manager import AccountManager
    from iris.kernel.manager import PluginManager


def build_room(manager: PluginManager) -> dict[str, object]:
    """Room Plugin の component を組み立てる。"""
    from iris.event.event_bus import EventBus as _EventBus
    from iris.room.batcher import RoomJoinBatcher
    from iris.room.dispatcher import _RoomDispatcher
    from iris.room.handler import _RoomEventHandler
    from iris.room.manager import RoomManager
    from iris.room.store import RoomStore

    store = RoomStore()
    event_bus = manager.resolve(_EventBus)

    join_batcher = RoomJoinBatcher(event_bus=event_bus)

    from iris.account.manager import AccountManager as _AccountMgr

    account_manager: AccountManager | None = manager.resolve_optional(_AccountMgr)

    room_manager = RoomManager(
        store=store,
        event_bus=event_bus,
        account_manager=account_manager,
        join_batcher=join_batcher,
    )

    dispatcher = _RoomDispatcher(room_manager=room_manager, account_manager=account_manager)

    event_handler = _RoomEventHandler(
        event_bus=event_bus,
        store=store,
        room_manager=room_manager,
        account_manager=account_manager,
    )

    return {
        "store": store,
        "event_bus": event_bus,
        "join_batcher": join_batcher,
        "room_manager": room_manager,
        "dispatcher": dispatcher,
        "event_handler": event_handler,
        "account_manager": account_manager,
    }


__all__ = ["build_room"]
