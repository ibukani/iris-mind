from __future__ import annotations

import pytest

from iris.account.models import Provider
from iris.event.event_bus import EventBus
from iris.io.events import ControlMessageEvent, InputReady, SessionDisconnectEvent
from iris.io.models import AuthMessage
from iris.io.session.manager import SessionManager
from iris.kernel.config import SessionConfig
from iris.memory.manager import MemoryManager
from iris.memory.models import system_event_block

pytestmark = pytest.mark.legacy


class DummyConnection:
    def close(self):
        pass


def test_session_manager_disconnect_publishes_session_disconnect_event():
    event_bus = EventBus()
    session_mgr = SessionManager(config=SessionConfig(access_token="test_token"), event_bus=event_bus)

    disconnect_events = []
    event_bus.subscribe(SessionDisconnectEvent, lambda ev: disconnect_events.append(ev))

    conn = DummyConnection()
    msg = AuthMessage(access_token="test_token", role="user", session_tag="test_user")
    resp = session_mgr.authenticate(conn, msg)
    assert resp.msg_type == "auth_success"
    session_id = resp.session_id

    session_mgr.remove_session(session_id)

    assert len(disconnect_events) == 1
    assert disconnect_events[0].session_id == session_id
    assert disconnect_events[0].session_tag == "test_user"


def test_handle_account_identify(event_bus: EventBus, wired_handlers) -> None:
    account_handler, _, account_provider, _ = wired_handlers

    resp = account_handler.handle_control_message(
        ControlMessageEvent(
            action="account.identify",
            identity={"provider": Provider.DISCORD, "subject": "123", "provider_name": "John"},
            source="test",
            timestamp=None,
        ),
    )

    assert resp is not None
    assert resp.action == "account.identified"
    assert len(resp.account_id) == 16
    assert resp.display_name == "John"
    account = account_provider.resolve(resp.account_id)
    assert account is not None
    assert account.display_name == "John"


def test_handle_account_profile(event_bus: EventBus, wired_handlers) -> None:
    _, _, account_provider, _ = wired_handlers
    account_handler = wired_handlers[0]

    account = account_provider.resolve_or_create_identity(Provider.DISCORD, "123", provider_name="John")

    resp = account_handler.handle_control_message(
        ControlMessageEvent(
            action="account.profile",
            account_id=account.account_id,
            source="test",
            timestamp=None,
        ),
    )

    assert resp is not None
    assert resp.action == "account.profile"
    assert resp.display_name == "John"


def test_account_update(event_bus: EventBus, wired_handlers) -> None:
    account_handler, _, account_provider, _ = wired_handlers

    account = account_provider.register("John")

    resp = account_handler.handle_control_message(
        ControlMessageEvent(
            action="account.update",
            account_id=account.account_id,
            display_name="Jane",
            source="test",
            timestamp=None,
        ),
    )

    assert resp is not None
    assert resp.action == "account.updated"
    assert resp.display_name == "Jane"

    updated = account_provider.resolve(account.account_id)
    assert updated is not None
    assert updated.display_name == "Jane"


def test_room_join_creates_system_event(event_bus: EventBus, wired_handlers) -> None:
    _, room_handler, account_provider, room_provider = wired_handlers

    room = room_provider.create_room("test")
    account = account_provider.resolve_or_create_identity(Provider.DISCORD, "123", provider_name="John")

    inputs_ready: list[InputReady] = []
    event_bus.subscribe(InputReady, lambda ev: inputs_ready.append(ev))

    resp = room_handler.handle_control_message(
        ControlMessageEvent(
            action="room.join",
            room_id=room.room_id,
            account_id=account.account_id,
            source="test",
            timestamp=None,
        ),
        session_id="s1",
    )

    assert resp is not None
    assert resp.action == "room.joined"

    assert len(inputs_ready) == 1
    assert "入室" in inputs_ready[0].content or "Joined" in inputs_ready[0].content


def test_room_leave_creates_system_event(event_bus: EventBus, wired_handlers) -> None:
    _, room_handler, account_provider, room_provider = wired_handlers

    room = room_provider.create_room("test")
    account = account_provider.resolve_or_create_identity(Provider.DISCORD, "123", provider_name="John")
    room_provider.join_room(room.room_id, account.account_id, session_id="s1")

    inputs_ready: list[InputReady] = []
    event_bus.subscribe(InputReady, lambda ev: inputs_ready.append(ev))

    resp = room_handler.handle_control_message(
        ControlMessageEvent(
            action="room.leave",
            room_id=room.room_id,
            account_id=account.account_id,
            source="test",
            timestamp=None,
        ),
        session_id="s1",
    )

    assert resp is not None
    assert resp.action == "room.left"

    assert len(inputs_ready) == 1
    assert "退室" in inputs_ready[0].content or "Left" in inputs_ready[0].content


def test_session_disconnect_triggers_auto_user_left(event_bus: EventBus, wired_handlers) -> None:
    _, _, account_provider, room_provider = wired_handlers

    room = room_provider.create_room("test")
    account = account_provider.register("Alice")
    account_id = account.account_id
    room_provider.join_room(room.room_id, account_id, session_id="sess1")

    inputs_ready: list[InputReady] = []
    event_bus.subscribe(InputReady, lambda ev: inputs_ready.append(ev))

    event_bus.publish(
        SessionDisconnectEvent(timestamp=None, source="session", session_id="sess1", session_tag="alice@example.com"),
    )

    assert len(inputs_ready) == 1
    text = inputs_ready[0].content
    assert "退室" in text
    assert "Alice" in text


def test_session_disconnect_no_users_no_error(event_bus: EventBus, wired_handlers) -> None:
    _ = wired_handlers

    inputs_ready: list[InputReady] = []
    event_bus.subscribe(InputReady, lambda ev: inputs_ready.append(ev))

    event_bus.publish(
        SessionDisconnectEvent(timestamp=None, source="session", session_id="empty_sess", session_tag="nobody"),
    )

    assert len(inputs_ready) == 0


def test_system_event_block_has_metadata():
    block = system_event_block(
        "[system] Bob が入室しました",
        event_type="room.joined",
        account_id="u123",
        display_name="Bob",
    )
    assert block["type"] == "system_event"
    assert block["text"] == "[system] Bob が入室しました"
    meta = block["metadata"]
    assert meta is not None
    assert meta["event_type"] == "room.joined"
    assert meta["account_id"] == "u123"
    assert meta["display_name"] == "Bob"


def test_short_term_room_user_mapping():
    memory_mgr = MemoryManager()
    memory_mgr.short_term.add_user("u1", "Alice", room_id="room-a")
    memory_mgr.short_term.add_user("u2", "Bob", room_id="room-a")
    memory_mgr.short_term.add_user("u3", "Carol", room_id="room-b")

    assert len(memory_mgr.short_term.get_users_by_room("room-a")) == 2
    assert len(memory_mgr.short_term.get_users_by_room("room-b")) == 1
    assert len(memory_mgr.short_term.get_users_by_room("room-c")) == 0

    memory_mgr.short_term.remove_user("u1", room_id="room-a")
    room_a_users = memory_mgr.short_term.get_users_by_room("room-a")
    assert len(room_a_users) == 1
    assert room_a_users[0].account_id == "u2"
