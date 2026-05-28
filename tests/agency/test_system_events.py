from __future__ import annotations

from datetime import datetime, timedelta

from iris.agency import LLMGateway
from iris.event.event_bus import EventBus
from iris.io.models import AuthMessage
from iris.io.session.manager import SessionManager
from iris.kernel.config import SessionConfig
from iris.llm.prompt import Personality
from iris.memory.handler import _MemoryEventHandler
from iris.memory.manager import MemoryManager
from iris.memory.user_store import UserStore


class DummyConnection:
    def close(self):
        pass


def test_session_manager_disconnect_no_auto_user_events():
    event_bus = EventBus()
    session_mgr = SessionManager(config=SessionConfig(access_token="test_token"), event_bus=event_bus)

    events = []
    event_bus.subscribe("MessageEvent", lambda ev: events.append(ev))

    conn = DummyConnection()
    msg = AuthMessage(access_token="test_token", role="user", identity="test_user")
    resp = session_mgr.authenticate(conn, msg)
    assert resp.msg_type == "auth_success"
    user_events = [e for e in events if e.msg_type in ("user_entered", "user_left")]
    assert len(user_events) == 0

    key = "user:test_user"
    session_mgr._last_disconnect_times[key] = datetime.now() - timedelta(hours=1, minutes=10)

    events.clear()
    resp = session_mgr.authenticate(conn, msg)
    assert resp.msg_type == "auth_success"
    user_events = [e for e in events if e.msg_type in ("user_entered", "user_left")]
    assert len(user_events) == 0


def test_handle_system_user_register():
    event_bus = EventBus()
    memory_mgr = MemoryManager()
    user_store = UserStore()
    event_handler = _MemoryEventHandler(
        event_bus,
        memory_mgr.sensory,
        None,
        short_term=memory_mgr.short_term,
        user_store=user_store,
    )

    resp = event_handler.handle_system_message(
        {"action": "user_register", "nickname": "John"},
        session_id="s1",
        role="external",
    )

    assert resp is not None
    assert resp["action"] == "user_register"
    assert len(resp["user_id"]) == 16
    assert resp["nickname"] == "John"
    assert resp["text"].startswith("Your user ID: ")
    assert user_store.get(resp["user_id"]) == "John"


def test_handle_system_user_entered():
    event_bus = EventBus()
    memory_mgr = MemoryManager()
    user_store = UserStore()
    user_id, _ = user_store.create("John")
    event_handler = _MemoryEventHandler(
        event_bus,
        memory_mgr.sensory,
        None,
        short_term=memory_mgr.short_term,
        user_store=user_store,
    )

    inputs_ready = []
    event_bus.subscribe("InputReady", lambda ev: inputs_ready.append(ev))

    resp = event_handler.handle_system_message(
        {"action": "user_entered", "user_id": user_id},
        session_id="s1",
        role="external",
    )

    assert resp is not None
    assert resp["action"] == "user_entered"
    assert resp["nickname"] == "John"
    assert "Welcome" in resp["text"]

    assert len(inputs_ready) == 1
    assert "[system]" in inputs_ready[0].content
    assert "John" in inputs_ready[0].content
    assert "入室" in inputs_ready[0].content


def test_handle_system_user_left():
    event_bus = EventBus()
    memory_mgr = MemoryManager()
    user_store = UserStore()
    user_id, _ = user_store.create("John")
    event_handler = _MemoryEventHandler(
        event_bus,
        memory_mgr.sensory,
        None,
        short_term=memory_mgr.short_term,
        user_store=user_store,
    )
    memory_mgr.short_term.add_user(user_id, "John")

    inputs_ready = []
    event_bus.subscribe("InputReady", lambda ev: inputs_ready.append(ev))

    resp = event_handler.handle_system_message(
        {"action": "user_left", "user_id": user_id},
        session_id="s1",
        role="external",
    )

    assert resp is not None
    assert resp["action"] == "user_left"
    assert "Goodbye" in resp["text"]

    assert len(inputs_ready) == 1
    assert "退室" in inputs_ready[0].content


def test_handle_system_nickname_update():
    event_bus = EventBus()
    memory_mgr = MemoryManager()
    user_store = UserStore()
    user_id, _ = user_store.create("John")
    event_handler = _MemoryEventHandler(
        event_bus,
        memory_mgr.sensory,
        None,
        short_term=memory_mgr.short_term,
        user_store=user_store,
    )
    memory_mgr.short_term.add_user(user_id, "John")

    inputs_ready = []
    event_bus.subscribe("InputReady", lambda ev: inputs_ready.append(ev))

    resp = event_handler.handle_system_message(
        {"action": "nickname_update", "user_id": user_id, "nickname": "Jane"},
        session_id="s1",
        role="external",
    )

    assert resp is not None
    assert resp["action"] == "nickname_update"
    assert resp["nickname"] == "Jane"
    assert "Jane" in resp["text"]

    assert user_store.get(user_id) == "Jane"
    assert len(inputs_ready) == 1
    assert "改名" in inputs_ready[0].content


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
