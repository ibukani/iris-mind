from __future__ import annotations

import pytest

from iris.room.models import Room, RoomMember, RoomState
from iris.room.store import RoomStore


@pytest.fixture
def tmp_store() -> RoomStore:
    return RoomStore()


class TestRoomStore:
    def test_add_and_find_room(self, tmp_store: RoomStore) -> None:
        room = Room(name="general")
        tmp_store.add_room(room)
        found = tmp_store.find_room_by_id(room.room_id)
        assert found is not None
        assert found.name == "general"

    def test_find_active_rooms(self, tmp_store: RoomStore) -> None:
        tmp_store.add_room(Room(name="active"))
        tmp_store.add_room(Room(name="archived", state=RoomState.ARCHIVED))
        active = tmp_store.find_active_rooms()
        assert len(active) == 1
        assert active[0].name == "active"

    def test_delete_room(self, tmp_store: RoomStore) -> None:
        room = Room(name="to_delete")
        tmp_store.add_room(room)
        tmp_store.delete_room(room.room_id)
        assert tmp_store.find_room_by_id(room.room_id) is None


class TestMemberStore:
    def test_add_and_find_member(self, tmp_store: RoomStore) -> None:
        member = RoomMember(room_id="r1", account_id="a1")
        tmp_store.add_member(member)
        found = tmp_store.find_member("r1", "a1")
        assert found is not None
        assert found.role == "member"

    def test_find_members_by_room(self, tmp_store: RoomStore) -> None:
        tmp_store.add_member(RoomMember(room_id="r1", account_id="a1"))
        tmp_store.add_member(RoomMember(room_id="r1", account_id="a2"))
        tmp_store.add_member(RoomMember(room_id="r2", account_id="a3"))
        members = tmp_store.find_members_by_room("r1")
        assert len(members) == 2

    def test_find_members_by_room_excludes_inactive(self, tmp_store: RoomStore) -> None:
        active = RoomMember(room_id="r1", account_id="a1")
        inactive = RoomMember(room_id="r1", account_id="a2", disconnected_at="2026-01-01T00:00:00+00:00")
        tmp_store.add_member(active)
        tmp_store.add_member(inactive)
        members = tmp_store.find_members_by_room("r1")
        assert [member.account_id for member in members] == ["a1"]

    def test_remove_member(self, tmp_store: RoomStore) -> None:
        tmp_store.add_member(RoomMember(room_id="r1", account_id="a1"))
        tmp_store.remove_member("r1", "a1")
        assert tmp_store.find_member("r1", "a1") is None

    def test_find_rooms_by_account(self, tmp_store: RoomStore) -> None:
        tmp_store.add_room(Room(room_id="r1", name="room1"))
        tmp_store.add_room(Room(room_id="r2", name="room2"))
        tmp_store.add_room(Room(room_id="r3", name="room3", state=RoomState.ARCHIVED))
        tmp_store.add_member(RoomMember(room_id="r1", account_id="a1"))
        tmp_store.add_member(RoomMember(room_id="r2", account_id="a1"))
        tmp_store.add_member(RoomMember(room_id="r3", account_id="a1"))
        rooms = tmp_store.find_rooms_by_account("a1")
        assert len(rooms) == 2
        assert {room.room_id for room in rooms} == {"r1", "r2"}
