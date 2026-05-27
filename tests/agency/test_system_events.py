from __future__ import annotations

from datetime import datetime, timedelta
import time

from iris.agency import LLMGateway, ProactiveScorer
from iris.event.event_bus import EventBus
from iris.event.event_types import ClientSessionEvent
from iris.io.models import AuthMessage
from iris.io.session.manager import SessionManager
from iris.kernel.config import Config, SessionConfig
from iris.llm.prompt import Personality
from iris.memory.handler import _MemoryEventHandler
from iris.memory.manager import MemoryManager


class DummyConnection:
    def close(self):
        pass


def test_session_manager_disconnect_time_and_events():
    event_bus = EventBus()
    session_mgr = SessionManager(config=SessionConfig(access_token="test_token"), event_bus=event_bus)

    events = []
    event_bus.subscribe("ClientSessionEvent", lambda ev: events.append(ev))

    conn = DummyConnection()
    msg = AuthMessage(access_token="test_token", role="user", identity="test_user")
    resp = session_mgr.authenticate(conn, msg)
    assert resp.msg_type == "auth_success"
    session_id = resp.session_id

    assert len(events) == 1
    assert events[0].action == "connected"
    assert events[0].offline_duration == ""

    events.clear()
    session_mgr.remove_session(session_id)
    assert len(events) == 1
    assert events[0].action == "disconnected"

    key = "user:test_user"
    session_mgr._last_disconnect_times[key] = datetime.now() - timedelta(hours=1, minutes=10)

    events.clear()
    resp = session_mgr.authenticate(conn, msg)
    assert resp.msg_type == "auth_success"
    assert len(events) == 1
    assert events[0].action == "connected"
    assert events[0].offline_duration == "1時間10分間"


def test_memory_manager_subscribes_client_session_event():
    event_bus = EventBus()
    memory_mgr = MemoryManager()
    _MemoryEventHandler(event_bus, memory_mgr.sensory, None)
    assert memory_mgr is not None

    inputs_ready = []
    event_bus.subscribe("InputReady", lambda ev: inputs_ready.append(ev))

    ev = ClientSessionEvent(
        timestamp=datetime.now(),
        source="session",
        session_id="session_123",
        action="connected",
        role="user",
        identity="test_user",
        offline_duration="2時間",
    )
    event_bus.publish(ev)

    assert len(inputs_ready) == 1
    ir = inputs_ready[0]
    assert ir.session_id == "session_123"
    assert ir.context.get("system_event") == "connected"
    assert ir.context.get("offline_duration") == "2時間"
    assert ir.context.get("role") == "user"


def test_scoring_with_system_event_context():
    event_bus = EventBus()
    cfg = Config()
    cfg.proactive.speak_threshold = 0.5
    memory_mgr = MemoryManager()
    _MemoryEventHandler(event_bus, memory_mgr.sensory, cfg.proactive)
    scoring = ProactiveScorer(config=cfg.proactive, memory=memory_mgr)

    context = {"system_event": "connected", "role": "user", "offline_duration": "3時間"}

    from iris.agency import ScoreContext

    total, _ = scoring.compute(
        ScoreContext(
            now=time.time(),
            context=context,
        )
    )
    assert total >= 0.6


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
