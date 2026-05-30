from __future__ import annotations

from iris.event.event_types import ControlMessageEvent
from iris.room.dispatcher import _RoomDispatcher
from iris.room.manager import RoomManager
from iris.room.models import RoomState
from iris.room.store import RoomStore


def _make_dispatcher() -> tuple[_RoomDispatcher, RoomManager]:
    store = RoomStore()
    room_manager = RoomManager(store=store)
    dispatcher = _RoomDispatcher(room_manager=room_manager)
    return dispatcher, room_manager


class TestRoomDispatcher:
    def test_join_missing_room_errors(self) -> None:
        dispatcher, _ = _make_dispatcher()
        resp = dispatcher.handle_control_message(
            ControlMessageEvent(action="room.join", room_id="missing", account_id="u1", source="test", timestamp=None),
            session_id="s1",
        )
        assert resp is not None
        assert resp.action == "room.join"
        assert "room not found" in resp.text

    def test_leave_missing_room_errors(self) -> None:
        dispatcher, _ = _make_dispatcher()
        resp = dispatcher.handle_control_message(
            ControlMessageEvent(action="room.leave", room_id="missing", account_id="u1", source="test", timestamp=None),
            session_id="s1",
        )
        assert resp is not None
        assert resp.action == "room.leave"
        assert "room not found" in resp.text

    def test_update_invalid_state_errors(self) -> None:
        dispatcher, room_manager = _make_dispatcher()
        room = room_manager.create_room("general")
        resp = dispatcher.handle_control_message(
            ControlMessageEvent(
                action="room.update",
                room_id=room.room_id,
                text='{"state":"broken"}',
                account_id="u1",
                source="test",
                timestamp=None,
            ),
            session_id="s1",
        )
        assert resp is not None
        assert resp.action == "room.update"
        assert "RoomState" in resp.text or "not a valid" in resp.text
        assert room_manager.get_room(room.room_id).state == RoomState.ACTIVE
