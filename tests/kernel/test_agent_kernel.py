from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest

from iris.kernel.agent_state import AgentStateManager, State
from iris.kernel.config import ProactiveConfig
from iris.kernel.core import AgentKernel, AnomalyDetector
from iris.kernel.event import (
    AgentAnomalyEvent,
    AgentResponseEvent,
    EventBus,
    ProactiveSpeechEvent,
    UserInputEvent,
)
from iris.kernel.services import ProactiveEngine
from tests.conftest import FakeMemoryManager

# ── AnomalyDetector ──────────────────────────────────────────


class TestAnomalyDetector:
    def test_record_speech_normal(self) -> None:
        detector = AnomalyDetector()
        flags = detector.record_speech()
        assert flags == []

    def test_record_speech_frequency_exceeded(self) -> None:
        now = 1000.0
        detector = AnomalyDetector(time_provider=lambda: now)
        for _ in range(6):
            detector.record_speech()
        flags = detector.record_speech()
        assert "frequency_exceeded" in flags

    def test_record_speech_window_expires(self) -> None:
        t = [100.0 * i for i in range(10)]
        idx = 0

        def time_provider() -> float:
            nonlocal idx
            v = t[idx]
            idx += 1
            return v

        detector = AnomalyDetector(time_provider=time_provider)
        for _ in range(6):
            detector.record_speech()
        flags = detector.record_speech()
        # Now in a new time window where old entries expired
        assert "frequency_exceeded" not in flags

    def test_check_frequency_no_records(self) -> None:
        detector = AnomalyDetector()
        assert detector.check_frequency() == []

    def test_check_frequency_below_threshold(self) -> None:
        detector = AnomalyDetector()
        detector.record_speech()
        detector.record_speech()
        flags = detector.check_frequency()
        assert "frequency_exceeded" not in flags

    def test_check_suppression_health_clear(self) -> None:
        detector = AnomalyDetector()
        status: dict[str, Any] = {
            "suppression": {"confirmation_mode": False, "consecutive_ignores": 0, "negative_mood_score": 0.0}
        }
        issues = detector.check_suppression_health(status)
        assert issues == []

    def test_check_suppression_health_confirmation_mode(self) -> None:
        detector = AnomalyDetector()
        status: dict[str, Any] = {
            "suppression": {"confirmation_mode": True, "consecutive_ignores": 0, "negative_mood_score": 0.0}
        }
        issues = detector.check_suppression_health(status)
        assert len(issues) == 1
        assert issues[0]["type"] == "confirmation_mode"

    def test_check_suppression_health_high_ignores(self) -> None:
        detector = AnomalyDetector()
        status: dict[str, Any] = {
            "suppression": {"confirmation_mode": False, "consecutive_ignores": 3, "negative_mood_score": 0.0}
        }
        issues = detector.check_suppression_health(status)
        assert any(i["type"] == "high_ignore_rate" for i in issues)

    def test_check_suppression_health_negative_mood(self) -> None:
        detector = AnomalyDetector()
        status: dict[str, Any] = {
            "suppression": {"confirmation_mode": False, "consecutive_ignores": 0, "negative_mood_score": 0.8}
        }
        issues = detector.check_suppression_health(status)
        assert any(i["type"] == "negative_mood" for i in issues)


# ── Helpers ──────────────────────────────────────────────────


@pytest.fixture
def kernel_setup() -> tuple[AgentKernel, EventBus, AgentStateManager, FakeMemoryManager]:
    eb = EventBus()
    st = AgentStateManager(event_bus=eb, timeout_seconds=99999)
    mem = FakeMemoryManager()
    cfg = ProactiveConfig(enabled=False)
    engine = ProactiveEngine(config=cfg, event_bus=eb, state_manager=st, memory=mem)
    kernel = AgentKernel(event_bus=eb, state_manager=st, proactive=engine, memory=mem, config=cfg)
    engine.set_approval_callback(kernel.evaluate_proactive_request)
    return kernel, eb, st, mem


# ── AgentKernel ──────────────────────────────────────────────


class TestAgentKernel:
    def test_startup_subscribes_events(self) -> None:
        eb = EventBus()
        st = AgentStateManager(event_bus=eb)
        mem = FakeMemoryManager()
        cfg = ProactiveConfig(enabled=False)
        engine = ProactiveEngine(config=cfg, event_bus=eb, state_manager=st, memory=mem)
        kernel = AgentKernel(event_bus=eb, state_manager=st, proactive=engine, memory=mem, config=cfg)
        kernel.startup()
        assert kernel._running is True
        kernel.shutdown()

    def test_shutdown_stops_timer(self) -> None:
        eb = EventBus()
        st = AgentStateManager(event_bus=eb)
        mem = FakeMemoryManager()
        cfg = ProactiveConfig(enabled=False)
        engine = ProactiveEngine(config=cfg, event_bus=eb, state_manager=st, memory=mem)
        kernel = AgentKernel(event_bus=eb, state_manager=st, proactive=engine, memory=mem, config=cfg)
        kernel.startup()
        kernel.shutdown()
        assert kernel._running is False

    def test_on_user_input_transitions_to_processing(self, kernel_setup) -> None:
        kernel, eb, st, mem = kernel_setup
        kernel._on_user_input(UserInputEvent(timestamp=datetime.now(), source="test", content="hello"))
        assert st.is_processing() is True

    def test_on_user_input_records_episodic(self, kernel_setup) -> None:
        kernel, eb, st, mem = kernel_setup
        kernel._on_user_input(UserInputEvent(timestamp=datetime.now(), source="test", content="hello"))
        assert mem.episodic.count == 1

    def test_on_user_input_ignored_when_not_idle(self, kernel_setup) -> None:
        kernel, eb, st, mem = kernel_setup
        st.transition(State.PROCESSING)
        kernel._on_user_input(UserInputEvent(timestamp=datetime.now(), source="test", content="hello"))
        assert mem.episodic.count == 0

    def test_on_agent_response_transitions_to_idle(self, kernel_setup) -> None:
        kernel, eb, st, mem = kernel_setup
        st.transition(State.PROCESSING)
        kernel._on_agent_response(AgentResponseEvent(timestamp=datetime.now(), source="test", content="response"))
        assert st.is_idle() is True

    def test_on_agent_response_records_episodic(self, kernel_setup) -> None:
        kernel, eb, st, mem = kernel_setup
        kernel._on_agent_response(AgentResponseEvent(timestamp=datetime.now(), source="test", content="response"))
        assert mem.episodic.count == 1

    def test_evaluate_proactive_request_approved(self, kernel_setup) -> None:
        kernel, eb, st, mem = kernel_setup
        result = kernel.evaluate_proactive_request({"time": 0.5}, 0.8, "time")
        assert result is True

    def test_evaluate_proactive_request_denied_when_processing(self, kernel_setup) -> None:
        kernel, eb, st, mem = kernel_setup
        st.transition(State.PROCESSING)
        result = kernel.evaluate_proactive_request({"time": 0.5}, 0.8, "time")
        assert result is False

    def test_on_proactive_speech_records_episodic(self, kernel_setup) -> None:
        kernel, eb, st, mem = kernel_setup
        kernel._on_proactive_speech(
            ProactiveSpeechEvent(
                timestamp=datetime.now(), source="test", content="hello", trigger_type="time", confidence=0.5
            )
        )
        assert mem.episodic.count == 1

    def test_on_proactive_speech_checks_anomaly(self) -> None:
        eb = EventBus()
        st = AgentStateManager(event_bus=eb)
        mem = FakeMemoryManager()
        cfg = ProactiveConfig(enabled=False)
        engine = ProactiveEngine(config=cfg, event_bus=eb, state_manager=st, memory=mem)
        kernel = AgentKernel(event_bus=eb, state_manager=st, proactive=engine, memory=mem, config=cfg)
        anomalies: list[AgentAnomalyEvent] = []

        def collect(event: AgentAnomalyEvent) -> None:
            anomalies.append(event)

        eb.subscribe("AgentAnomalyEvent", collect)
        for _ in range(6):
            kernel._on_proactive_speech(
                ProactiveSpeechEvent(
                    timestamp=datetime.now(), source="test", content="x", trigger_type="time", confidence=0.5
                )
            )
        assert any(a.anomaly_type == "frequency_exceeded" for a in anomalies)
