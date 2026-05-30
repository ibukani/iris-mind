from __future__ import annotations

from iris.room.models import Room, RoomMember, RoomState


class TestRoomModel:
    def test_auto_generate_id(self) -> None:
        r = Room(name="test")
        assert len(r.room_id) == 16
        assert r.name == "test"
        assert r.state == RoomState.ACTIVE

    def test_to_dict_roundtrip(self) -> None:
        r = Room(name="general", description="General channel", topic="General discussion")
        d = r.to_dict()
        restored = Room.from_dict(d)
        assert restored.room_id == r.room_id
        assert restored.name == "general"
        assert restored.description == "General channel"
        assert restored.topic == "General discussion"
        assert restored.state == RoomState.ACTIVE

    def test_archived_state(self) -> None:
        r = Room(name="old", state=RoomState.ARCHIVED)
        d = r.to_dict()
        restored = Room.from_dict(d)
        assert restored.state == RoomState.ARCHIVED


class TestRoomMemberModel:
    def test_auto_joined_at(self) -> None:
        m = RoomMember(room_id="r1", account_id="a1")
        assert m.joined_at != ""
        assert m.role == "member"

    def test_to_dict_roundtrip(self) -> None:
        m = RoomMember(room_id="r1", account_id="a1", role="owner")
        d = m.to_dict()
        restored = RoomMember.from_dict(d)
        assert restored.room_id == "r1"
        assert restored.account_id == "a1"
        assert restored.role == "owner"
