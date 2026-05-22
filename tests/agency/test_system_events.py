from __future__ import annotations

from datetime import datetime, timedelta
import time

from iris.agency.execution.inhibition import InhibitionController
from iris.agency.execution.pipeline import LLMPipeline
from iris.agency.planning.scoring import ProactiveScoring
from iris.event.event_bus import EventBus
from iris.event.event_types import ClientSessionEvent
from iris.io.models import AuthMessage
from iris.io.session.manager import SessionManager
from iris.kernel.config import Config, SessionConfig
from iris.llm.prompt_builder import Personality
from iris.memory.manager import MemoryManager


class DummyConnection:
    def close(self):
        pass


def test_session_manager_disconnect_time_and_events():
    event_bus = EventBus()
    session_mgr = SessionManager(config=SessionConfig(access_token="test_token"), event_bus=event_bus)

    events = []
    event_bus.subscribe("ClientSessionEvent", lambda ev: events.append(ev))

    # 1. 最初の接続
    conn = DummyConnection()
    msg = AuthMessage(access_token="test_token", role="user", identity="test_user")
    resp = session_mgr.authenticate(conn, msg)
    assert resp.msg_type == "auth_success"
    session_id = resp.session_id

    assert len(events) == 1
    assert events[0].action == "connected"
    assert events[0].offline_duration == ""

    # 2. 切断
    events.clear()
    session_mgr.remove_session(session_id)
    assert len(events) == 1
    assert events[0].action == "disconnected"

    # 3. 過去の切断時間を細工して、1時間10分後に再接続したことにする
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
    memory_mgr = MemoryManager(event_bus=event_bus)
    assert memory_mgr is not None

    inputs_ready = []
    event_bus.subscribe("InputReady", lambda ev: inputs_ready.append(ev))

    # クライアント接続イベント発行
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


def test_inhibition_controller_cooldown_and_planning_scoring():
    event_bus = EventBus()
    inhibition = InhibitionController()
    assert inhibition is not None

    # ProactiveConfigのspeak_thresholdは0.5と仮定
    cfg = Config()
    cfg.proactive.speak_threshold = 0.5
    memory_mgr = MemoryManager(event_bus=event_bus, proactive_config=cfg.proactive)
    scoring = ProactiveScoring(config=cfg.proactive, memory=memory_mgr)

    # 接続イベント付きの評価
    context = {"system_event": "connected", "role": "user", "offline_duration": "3時間"}

    total, _ = scoring.compute(
        now=time.time(), last_proactive_time=0.0, last_user_activity=0.0, negative_mood_score=0.0, context=context
    )
    # 接続イベント時は強制的に speak_threshold + 0.1 を超える
    assert total >= 0.6


def test_pipeline_injects_datetime():
    pipeline = LLMPipeline(
        llm=None,  # type: ignore
        model_config=None,  # type: ignore
        personality=Personality(),
        memory=None,
        limbic=None,
    )
    prompt = pipeline._prompt_builder.build(context_hint="テストコンテキスト")
    assert "## 現在日時" in prompt
    assert "テストコンテキスト" in prompt
