from __future__ import annotations

from unittest.mock import MagicMock

from iris.event.event_bus import EventBus
from iris.io.handler import _IOEventHandler
from iris.io.models import AuthMessage, Permission
from iris.io.session.manager import SessionManager
from iris.room.events import RoomJoinedEvent, RoomLeftEvent


def test_room_joined_event_broadcasts_presence() -> None:
    bus = EventBus()
    session_manager = SessionManager()
    conn = MagicMock()
    session_manager.authenticate(conn, AuthMessage(role="discord", permissions=[Permission.PERMISSION_RECEIVE_CHAT]))
    _IOEventHandler(event_bus=bus, session_manager=session_manager)

    bus.publish(
        RoomJoinedEvent(
            timestamp=None,
            source="room",
            room_id="room1",
            account_id="a1",
            display_name="Alice",
        ),
    )

    conn.send_bytes.assert_called_once()
    raw = conn.send_bytes.call_args.args[0].decode("utf-8")
    assert '"action":"presence.joined"' in raw
    assert '"account_id":"a1"' in raw
    assert '"display_name":"Alice"' in raw


def test_room_left_event_broadcasts_presence() -> None:
    bus = EventBus()
    session_manager = SessionManager()
    conn = MagicMock()
    session_manager.authenticate(conn, AuthMessage(role="discord", permissions=[Permission.PERMISSION_RECEIVE_CHAT]))
    _IOEventHandler(event_bus=bus, session_manager=session_manager)

    bus.publish(
        RoomLeftEvent(
            timestamp=None,
            source="room",
            room_id="room1",
            account_id="a1",
            display_name="Alice",
        ),
    )

    conn.send_bytes.assert_called_once()
    raw = conn.send_bytes.call_args.args[0].decode("utf-8")
    assert '"action":"presence.left"' in raw
    assert '"account_id":"a1"' in raw
