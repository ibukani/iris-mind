from __future__ import annotations

from iris.account.manager import AccountManager
from iris.account.models import Provider
from iris.account.store import AccountStore
from iris.event.event_bus import EventBus
from iris.event.event_types import Identity, MessageEvent
from iris.room.handler import _RoomEventHandler
from iris.room.manager import RoomManager
from iris.room.store import RoomStore


class TestRoomEventHandler:
    def test_message_event_resolves_account_id_from_speaker(self, tmp_path) -> None:
        event_bus = EventBus()
        account_store = AccountStore(
            accounts_path=str(tmp_path / "accounts.jsonl"),
            identities_path=str(tmp_path / "identities.jsonl"),
        )
        account_manager = AccountManager(store=account_store, event_bus=event_bus)
        room_store = RoomStore()
        room_manager = RoomManager(store=room_store, event_bus=event_bus, account_manager=account_manager)
        room = room_manager.create_room("general")
        event = MessageEvent(
            timestamp=None,
            source="io",
            session_id="s1",
            source_role="external",
            target_role="mind",
            account_id="",
            direction="request",
            msg_type="chat",
            content="hello",
            room_id=room.room_id,
            speaker=Identity(provider=Provider.DISCORD.value, subject="123", provider_name="John"),
        )

        handler = _RoomEventHandler(
            event_bus=event_bus,
            store=room_store,
            room_manager=room_manager,
            account_manager=account_manager,
        )
        handler._on_message_event(event)

        account = account_manager.resolve_or_create_identity(Provider.DISCORD, "123", provider_name="John")
        assert event.account_id == account.account_id
        assert room_manager.is_member(room.room_id, account.account_id)
