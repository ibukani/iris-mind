from __future__ import annotations

from datetime import UTC, datetime

from iris.event.event_bus import EventBus
from iris.event.event_types import SessionDisconnectEvent, TimerTick
from iris.room.handler import _RoomEventHandler
from iris.room.manager import RoomManager
from iris.room.models import RoomMember
from iris.room.store import RoomStore


def _make_manager() -> tuple[RoomManager, RoomStore]:
    store = RoomStore()
    manager = RoomManager(store=store)
    return manager, store


class TestRoomManagerCleanup:
    def test_auto_delete_when_last_member_leaves(self) -> None:
        manager, store = _make_manager()
        room = manager.create_room("test-room", created_by="user1")
        manager.join_room(room.room_id, "u1", session_id="s1")
        assert store.find_room_by_id(room.room_id) is not None

        result = manager.leave_room(room.room_id, "u1")

        assert result is True
        assert store.find_room_by_id(room.room_id) is None

    def test_default_room_not_auto_deleted(self) -> None:
        manager, store = _make_manager()
        room = manager.create_room("default", created_by="system")
        manager.join_room(room.room_id, "u1", session_id="s1")

        manager.leave_room(room.room_id, "u1")

        assert store.find_room_by_id(room.room_id) is not None

    def test_system_room_not_auto_deleted(self) -> None:
        manager, store = _make_manager()
        room = manager.create_room("system-bridge", created_by="system")
        manager.join_room(room.room_id, "u1", session_id="s1")

        manager.leave_room(room.room_id, "u1")

        assert store.find_room_by_id(room.room_id) is not None

    def test_room_not_deleted_when_members_remain(self) -> None:
        manager, store = _make_manager()
        room = manager.create_room("multi-user")
        manager.join_room(room.room_id, "u1", session_id="s1")
        manager.join_room(room.room_id, "u2", session_id="s2")

        manager.leave_room(room.room_id, "u1")

        assert store.find_room_by_id(room.room_id) is not None
        assert manager.is_member(room.room_id, "u2")

    def test_session_removal_does_not_delete(self) -> None:
        manager, store = _make_manager()
        room = manager.create_room("multi-session")
        manager.join_room(room.room_id, "u1", session_id="s1")
        manager.join_room(room.room_id, "u1", session_id="s2")

        result = manager.leave_room(room.room_id, "u1", session_id="s1")

        assert result is True
        assert store.find_room_by_id(room.room_id) is not None
        member = store.find_member(room.room_id, "u1")
        assert member is not None
        assert member.is_active

    def test_leave_event_publishes_room_deleted_on_empty(self) -> None:
        event_bus = EventBus()
        store = RoomStore()
        manager = RoomManager(store=store, event_bus=event_bus)
        room = manager.create_room("ephemeral", created_by="user1")
        manager.join_room(room.room_id, "u1", session_id="s1")

        deleted_ids: list[str] = []

        def _on_deleted(e: object) -> None:
            if hasattr(e, "room_id"):
                deleted_ids.append(str(e.room_id))

        event_bus.subscribe("RoomDeletedEvent", _on_deleted)

        manager.leave_room(room.room_id, "u1")

        assert room.room_id in deleted_ids


class TestRoomEventHandlerCleanup:
    def test_session_disconnect_deletes_empty_room(self) -> None:
        event_bus = EventBus()
        store = RoomStore()
        manager = RoomManager(store=store, event_bus=event_bus)
        _RoomEventHandler(
            event_bus=event_bus,
            store=store,
            room_manager=manager,
        )
        room = manager.create_room("temp-room", created_by="user1")
        manager.join_room(room.room_id, "u1", session_id="s1")

        event_bus.publish(
            SessionDisconnectEvent(
                timestamp=datetime.now(UTC),
                source="test",
                session_id="s1",
            ),
        )

        assert store.find_room_by_id(room.room_id) is None

    def test_session_disconnect_preserves_room_when_other_members_remain(self) -> None:
        event_bus = EventBus()
        store = RoomStore()
        manager = RoomManager(store=store, event_bus=event_bus)
        _RoomEventHandler(
            event_bus=event_bus,
            store=store,
            room_manager=manager,
        )
        room = manager.create_room("shared-room", created_by="user1")
        manager.join_room(room.room_id, "u1", session_id="s1")
        manager.join_room(room.room_id, "u2", session_id="s2")

        event_bus.publish(
            SessionDisconnectEvent(
                timestamp=datetime.now(UTC),
                source="test",
                session_id="s1",
            ),
        )

        assert store.find_room_by_id(room.room_id) is not None
        assert manager.is_member(room.room_id, "u2")

    def test_periodic_cleanup_deletes_empty_rooms(self) -> None:
        event_bus = EventBus()
        store = RoomStore()
        manager = RoomManager(store=store, event_bus=event_bus)
        handler = _RoomEventHandler(
            event_bus=event_bus,
            store=store,
            room_manager=manager,
        )
        room = manager.create_room("orphan", created_by="user1")
        store.add_member(RoomMember(room_id=room.room_id, account_id="u1", disconnected_at="2026-01-01T00:00:00+00:00"))

        for i in range(12):
            if i == 11:
                handler._cleanup_counter = 11
            event_bus.publish(TimerTick(timestamp=None, source="test", tick_count=i))

        assert store.find_room_by_id(room.room_id) is None

    def test_periodic_cleanup_preserves_protected_rooms(self) -> None:
        event_bus = EventBus()
        store = RoomStore()
        manager = RoomManager(store=store, event_bus=event_bus)
        handler = _RoomEventHandler(
            event_bus=event_bus,
            store=store,
            room_manager=manager,
        )
        default = manager.create_room("default", created_by="system")
        system = manager.create_room("bridge", created_by="system")
        store.add_member(
            RoomMember(room_id=default.room_id, account_id="u1", disconnected_at="2026-01-01T00:00:00+00:00")
        )
        store.add_member(
            RoomMember(room_id=system.room_id, account_id="u1", disconnected_at="2026-01-01T00:00:00+00:00")
        )

        for i in range(24):
            if i == 11 or i == 23:
                handler._cleanup_counter = 11
            event_bus.publish(TimerTick(timestamp=None, source="test", tick_count=i))

        assert store.find_room_by_id(default.room_id) is not None
        assert store.find_room_by_id(system.room_id) is not None

    def test_periodic_cleanup_preserves_rooms_with_members(self) -> None:
        event_bus = EventBus()
        store = RoomStore()
        manager = RoomManager(store=store, event_bus=event_bus)
        handler = _RoomEventHandler(
            event_bus=event_bus,
            store=store,
            room_manager=manager,
        )
        room = manager.create_room("active-room", created_by="user1")
        manager.join_room(room.room_id, "u1", session_id="s1")

        for i in range(12):
            if i == 11:
                handler._cleanup_counter = 11
            event_bus.publish(TimerTick(timestamp=None, source="test", tick_count=i))

        assert store.find_room_by_id(room.room_id) is not None
