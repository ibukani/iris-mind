from __future__ import annotations

from unittest.mock import MagicMock

from iris.account.events import AccountPresenceEvent
from iris.event.event_bus import EventBus
from iris.io.handler import _IOEventHandler
from iris.io.models import AuthMessage, Permission
from iris.io.session.manager import SessionManager


def test_account_presence_event_broadcasts_system_message() -> None:
    bus = EventBus()
    session_manager = SessionManager()
    conn = MagicMock()
    session_manager.authenticate(conn, AuthMessage(role="discord", permissions=[Permission.PERMISSION_RECEIVE_CHAT]))
    _IOEventHandler(event_bus=bus, session_manager=session_manager)

    bus.publish(
        AccountPresenceEvent(
            timestamp=None,
            source="account",
            session_id="s1",
            account_id="a1",
            nickname="Alice",
            state="entered",
            provider="discord",
            subject="123",
        ),
    )

    conn.send_bytes.assert_called_once()
    raw = conn.send_bytes.call_args.args[0].decode("utf-8")
    assert '"action":"presence.joined"' in raw
    assert '"account_id":"a1"' in raw
    assert '"provider":"discord"' in raw
    assert '"subject":"123"' in raw
