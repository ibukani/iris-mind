from __future__ import annotations

from pathlib import Path

from iris.account.handler import _AccountEventHandler
from iris.account.provider import AccountProvider
from iris.account.store import AccountStore
from iris.agency import LLMGateway
from iris.event.event_bus import EventBus
from iris.io.models import AuthMessage, SystemMessage
from iris.io.session.manager import SessionManager
from iris.kernel.config import SessionConfig
from iris.llm.prompt import Personality
from iris.memory.handler import _MemoryEventHandler
from iris.memory.manager import MemoryManager
from iris.memory.models import system_event_block


class DummyConnection:
    def close(self):
        pass


def _make_handler(event_bus: EventBus, memory_mgr: MemoryManager, tmp_path: Path):
    store = AccountStore(
        accounts_path=str(tmp_path / "accounts.jsonl"),
        identities_path=str(tmp_path / "identities.jsonl"),
        bindings_path=str(tmp_path / "bindings.jsonl"),
    )
    provider = AccountProvider(store=store, event_bus=event_bus)
    account_handler = _AccountEventHandler(account_provider=provider, short_term=memory_mgr.short_term)
    handler = _MemoryEventHandler(
        event_bus,
        memory_mgr.sensory,
        None,
        short_term=memory_mgr.short_term,
        account_handler=account_handler,
    )
    return handler, provider


def test_session_manager_disconnect_publishes_session_disconnect_event():
    event_bus = EventBus()
    session_mgr = SessionManager(config=SessionConfig(access_token="test_token"), event_bus=event_bus)

    disconnect_events = []
    event_bus.subscribe("SessionDisconnectEvent", lambda ev: disconnect_events.append(ev))

    conn = DummyConnection()
    msg = AuthMessage(access_token="test_token", role="user", identity="test_user")
    resp = session_mgr.authenticate(conn, msg)
    assert resp.msg_type == "auth_success"
    session_id = resp.session_id

    session_mgr.remove_session(session_id)

    assert len(disconnect_events) == 1
    assert disconnect_events[0].session_id == session_id
    assert disconnect_events[0].identity == "test_user"


def test_handle_system_account_identify(tmp_path):
    event_bus = EventBus()
    memory_mgr = MemoryManager()
    handler, provider = _make_handler(event_bus, memory_mgr, tmp_path)

    sys_events = []
    event_bus.subscribe("SystemMessageEvent", lambda ev: sys_events.append(ev))

    resp = handler.handle_system_message(
        SystemMessage(
            action="account.identify",
            identity={"provider": "discord", "subject": "123", "display_name": "John"},
        ),
        session_id="s1",
    )

    assert resp is not None
    assert resp.action == "account.identify"
    assert len(resp.account_id) == 16
    assert resp.nickname == "John"
    account = provider.resolve(resp.account_id)
    assert account is not None
    assert account.nickname == "John"

    assert len(sys_events) == 1
    assert sys_events[0].action == "account.identify"


def test_handle_system_account_get(tmp_path):
    event_bus = EventBus()
    memory_mgr = MemoryManager()
    handler, provider = _make_handler(event_bus, memory_mgr, tmp_path)
    account = provider.resolve_or_create_identity("discord", "123", display_name="John")
    provider.bind_session("s1", account.account_id)

    sys_events = []
    event_bus.subscribe("SystemMessageEvent", lambda ev: sys_events.append(ev))

    resp = handler.handle_system_message(
        SystemMessage(action="account.get"),
        session_id="s1",
    )

    assert resp is not None
    assert resp.action == "account.get"
    assert resp.nickname == "John"

    assert len(sys_events) == 1
    assert sys_events[0].action == "account.get"


def test_handle_system_user_left(tmp_path):
    event_bus = EventBus()
    memory_mgr = MemoryManager()
    handler, provider = _make_handler(event_bus, memory_mgr, tmp_path)
    account = provider.register("John")
    user_id = account.account_id
    memory_mgr.short_term.add_user(user_id, "John")

    inputs_ready = []
    event_bus.subscribe("InputReady", lambda ev: inputs_ready.append(ev))

    resp = handler.handle_system_message(
        SystemMessage(action="account.leave", account_id=user_id),
        session_id="s1",
    )

    assert resp is not None
    assert resp.action == "account.leave"
    assert "Left" in resp.text

    assert len(inputs_ready) == 1
    assert "退室" in inputs_ready[0].content or "Left" in inputs_ready[0].content


def test_handle_system_account_update(tmp_path):
    event_bus = EventBus()
    memory_mgr = MemoryManager()
    handler, provider = _make_handler(event_bus, memory_mgr, tmp_path)
    account = provider.register("John")
    user_id = account.account_id
    memory_mgr.short_term.add_user(user_id, "John")

    inputs_ready = []
    event_bus.subscribe("InputReady", lambda ev: inputs_ready.append(ev))

    resp = handler.handle_system_message(
        SystemMessage(action="account.update", account_id=user_id, nickname="Jane"),
        session_id="s1",
    )

    assert resp is not None
    assert resp.action == "account.update"
    assert resp.nickname == "Jane"
    assert "Jane" in resp.text

    updated = provider.resolve(user_id)
    assert updated is not None
    assert updated.nickname == "Jane"
    assert len(inputs_ready) == 1
    assert "改名" in inputs_ready[0].content or "Jane" in inputs_ready[0].content


def test_session_disconnect_triggers_auto_user_left(tmp_path):
    event_bus = EventBus()
    memory_mgr = MemoryManager()
    _, provider = _make_handler(event_bus, memory_mgr, tmp_path)
    account = provider.register("Alice")
    user_id = account.account_id
    memory_mgr.short_term.add_user(user_id, "Alice", session_id="sess1")

    inputs_ready = []
    inhibition_events = []
    event_bus.subscribe("InputReady", lambda ev: inputs_ready.append(ev))
    event_bus.subscribe("InhibitionEvent", lambda ev: inhibition_events.append(ev))

    from iris.event.event_types import SessionDisconnectEvent

    event_bus.publish(
        SessionDisconnectEvent(timestamp=None, source="session", session_id="sess1", identity="alice@example.com"),
    )

    assert len(inputs_ready) == 1
    text = inputs_ready[0].content
    assert "退室" in text
    assert "Alice" in text
    assert memory_mgr.short_term.get_active_users() == []
    unsuppress = [e for e in inhibition_events if e.action.value == "unsuppress"]
    assert len(unsuppress) >= 1


def test_session_disconnect_no_users_no_error(tmp_path):
    event_bus = EventBus()
    memory_mgr = MemoryManager()
    _make_handler(event_bus, memory_mgr, tmp_path)

    inputs_ready = []
    event_bus.subscribe("InputReady", lambda ev: inputs_ready.append(ev))

    from iris.event.event_types import SessionDisconnectEvent

    event_bus.publish(
        SessionDisconnectEvent(timestamp=None, source="session", session_id="empty_sess", identity="nobody"),
    )

    assert len(inputs_ready) == 0


def test_system_event_block_has_metadata():
    block = system_event_block(
        "[system] Bob が入室しました",
        event_type="account.identify",
        user_id="u123",
        nickname="Bob",
    )
    assert block["type"] == "system_event"
    assert block["text"] == "[system] Bob が入室しました"
    meta = block["metadata"]
    assert meta is not None
    assert meta["event_type"] == "account.identify"
    assert meta["user_id"] == "u123"
    assert meta["nickname"] == "Bob"


def test_short_term_session_user_mapping():
    memory_mgr = MemoryManager()
    memory_mgr.short_term.add_user("u1", "Alice", session_id="s1")
    memory_mgr.short_term.add_user("u2", "Bob", session_id="s1")
    memory_mgr.short_term.add_user("u3", "Carol", session_id="s2")

    assert len(memory_mgr.short_term.get_users_by_session("s1")) == 2
    assert len(memory_mgr.short_term.get_users_by_session("s2")) == 1
    assert len(memory_mgr.short_term.get_users_by_session("s3")) == 0

    memory_mgr.short_term.remove_user("u1")
    s1_users = memory_mgr.short_term.get_users_by_session("s1")
    assert len(s1_users) == 1
    assert s1_users[0][0] == "u2"


def test_pipeline_injects_datetime():
    pipeline = LLMGateway(
        llm=None,  # type: ignore
        model_config=None,  # type: ignore
        personality=Personality(),
        memory=None,
    )
    sys_msgs = pipeline._prompt_builder.build(context_hint="テストコンテキスト")
    combined = "\n\n".join(str(m.content) for m in sys_msgs)
    assert "## 現在日時" in combined
    assert "テストコンテキスト" in combined
