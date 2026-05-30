from __future__ import annotations

import pytest

from iris.room.manager import RoomManager
from iris.room.models import RoomState
from iris.room.store import RoomStore


@pytest.fixture
def tmp_provider() -> RoomManager:
    store = RoomStore()
    return RoomManager(store=store)


class TestRoomManager:
    def test_create_room(self, tmp_provider: RoomManager) -> None:
        room = tmp_provider.create_room("general", created_by="user1")
        assert room.name == "general"
        assert room.created_by == "user1"
        assert len(room.room_id) == 16

    def test_get_room(self, tmp_provider: RoomManager) -> None:
        room = tmp_provider.create_room("test")
        found = tmp_provider.get_room(room.room_id)
        assert found is not None
        assert found.name == "test"

    def test_list_rooms(self, tmp_provider: RoomManager) -> None:
        tmp_provider.create_room("active")
        tmp_provider.create_room("archived")
        tmp_provider.archive_room(tmp_provider.create_room("old").room_id)
        active = tmp_provider.list_rooms()
        assert len(active) == 2

    def test_update_room(self, tmp_provider: RoomManager) -> None:
        room = tmp_provider.create_room("old_name")
        tmp_provider.update_room(room.room_id, name="new_name")
        updated = tmp_provider.get_room(room.room_id)
        assert updated is not None
        assert updated.name == "new_name"

    def test_archive_room(self, tmp_provider: RoomManager) -> None:
        room = tmp_provider.create_room("to_archive")
        tmp_provider.archive_room(room.room_id)
        archived = tmp_provider.get_room(room.room_id)
        assert archived is not None
        assert archived.state == RoomState.ARCHIVED

    def test_delete_room(self, tmp_provider: RoomManager) -> None:
        room = tmp_provider.create_room("to_delete")
        tmp_provider.delete_room(room.room_id)
        assert tmp_provider.get_room(room.room_id) is None


class TestRoomMembership:
    def test_join_room(self, tmp_provider: RoomManager) -> None:
        room = tmp_provider.create_room("test")
        tmp_provider.join_room(room.room_id, "user1", session_id="s1")
        assert tmp_provider.is_member(room.room_id, "user1")

    def test_leave_room(self, tmp_provider: RoomManager) -> None:
        room = tmp_provider.create_room("test")
        tmp_provider.join_room(room.room_id, "user1", session_id="s1")
        tmp_provider.leave_room(room.room_id, "user1", session_id="s1")
        assert not tmp_provider.is_member(room.room_id, "user1")

    def test_get_members(self, tmp_provider: RoomManager) -> None:
        room = tmp_provider.create_room("test")
        tmp_provider.join_room(room.room_id, "user1", session_id="s1")
        tmp_provider.join_room(room.room_id, "user2", session_id="s2")
        members = tmp_provider.get_members(room.room_id)
        assert len(members) == 2

    def test_get_rooms_by_account(self, tmp_provider: RoomManager) -> None:
        room1 = tmp_provider.create_room("room1")
        room2 = tmp_provider.create_room("room2")
        tmp_provider.join_room(room1.room_id, "user1", session_id="s1")
        tmp_provider.join_room(room2.room_id, "user1", session_id="s2")
        rooms = tmp_provider.get_rooms_by_account("user1")
        assert len(rooms) == 2
