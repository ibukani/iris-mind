from __future__ import annotations

from typing import Any, cast

import pytest

from iris.kernel.agent_state import AgentStateManager, State
from iris.kernel.config import ProactiveConfig
from iris.kernel.core import AgentKernel, AnomalyDetector
from iris.kernel.event import AgentAnomalyEvent, EventBus
from iris.kernel.io.models import InputMessage
from iris.kernel.services import ProactiveEngine, ProactiveResult
from tests.conftest import FakeMemoryManager, FakeOutputManager

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
    st = AgentStateManager(event_bus=eb, timeout_seconds=cast(dict, 99999))
    mem = cast(Any, FakeMemoryManager())
    out = cast(Any, FakeOutputManager())
    cfg = ProactiveConfig(enabled=False)
    engine = ProactiveEngine(config=cfg, event_bus=eb, output_manager=out, state_manager=st, memory=mem)
    kernel = AgentKernel(event_bus=eb, state_manager=st, proactive=engine, memory=mem, config=cfg, output_manager=out)
    engine.set_approval_callback(kernel.evaluate_proactive_request)
    return kernel, eb, st, mem


# ── AgentKernel ──────────────────────────────────────────────


class TestAgentKernel:
    def test_startup_subscribes_events(self) -> None:
        eb = EventBus()
        st = AgentStateManager(event_bus=eb)
        mem = cast(Any, FakeMemoryManager())
        out = cast(Any, FakeOutputManager())
        cfg = ProactiveConfig(enabled=False)
        engine = ProactiveEngine(config=cfg, event_bus=eb, output_manager=out, state_manager=st, memory=mem)
        kernel = AgentKernel(
            event_bus=eb, state_manager=st, proactive=engine, memory=mem, config=cfg, output_manager=out
        )
        kernel.startup()
        assert kernel._running is True
        kernel.shutdown()

    def test_shutdown_stops_timer(self) -> None:
        eb = EventBus()
        st = AgentStateManager(event_bus=eb)
        mem = cast(Any, FakeMemoryManager())
        out = cast(Any, FakeOutputManager())
        cfg = ProactiveConfig(enabled=False)
        engine = ProactiveEngine(config=cfg, event_bus=eb, output_manager=out, state_manager=st, memory=mem)
        kernel = AgentKernel(
            event_bus=eb, state_manager=st, proactive=engine, memory=mem, config=cfg, output_manager=out
        )
        kernel.startup()
        kernel.shutdown()
        assert kernel._running is False

    def test_on_user_input_transitions_to_processing(self, kernel_setup) -> None:
        kernel, eb, st, mem = kernel_setup
        kernel.on_input(InputMessage(source="test", content="hello"))
        assert st.is_processing() is True

    def test_on_user_input_records_episodic(self, kernel_setup) -> None:
        kernel, eb, st, mem = kernel_setup
        kernel.on_input(InputMessage(source="test", content="hello"))
        assert mem.episodic.count == 1

    def test_on_user_input_ignored_when_not_idle(self, kernel_setup) -> None:
        kernel, eb, st, mem = kernel_setup
        st.transition(State.PROCESSING)
        kernel.on_input(InputMessage(source="test", content="hello"))
        assert mem.episodic.count == 0

    def test_on_response_complete_transitions_to_idle(self, kernel_setup) -> None:
        kernel, eb, st, mem = kernel_setup
        st.transition(State.PROCESSING)
        kernel.on_response_complete(content="response")
        assert st.is_idle() is True

    def test_on_response_complete_records_episodic(self, kernel_setup) -> None:
        kernel, eb, st, mem = kernel_setup
        kernel.on_response_complete(content="response")
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
        kernel.on_proactive_speech(
            ProactiveResult(content="hello", tier=1, confidence=0.5, trigger_type="time", reasoning="test")
        )
        assert mem.episodic.count == 1

    def test_on_proactive_speech_checks_anomaly(self) -> None:
        eb = EventBus()
        st = AgentStateManager(event_bus=eb)
        mem = cast(Any, FakeMemoryManager())
        out = cast(Any, FakeOutputManager())
        cfg = ProactiveConfig(enabled=False)
        engine = ProactiveEngine(config=cfg, event_bus=eb, output_manager=out, state_manager=st, memory=mem)
        kernel = AgentKernel(
            event_bus=eb, state_manager=st, proactive=engine, memory=mem, config=cfg, output_manager=out
        )
        anomalies: list[AgentAnomalyEvent] = []

        def collect(event: AgentAnomalyEvent) -> None:
            anomalies.append(event)

        eb.subscribe("AgentAnomalyEvent", collect)
        for _ in range(6):
            kernel.on_proactive_speech(
                ProactiveResult(content="x", tier=1, confidence=0.5, trigger_type="time", reasoning="test")
            )
        assert any(a.anomaly_type == "frequency_exceeded" for a in anomalies)
        # Anomaly should also send error to OutputManager
        assert any(m.msg_type == "error" for m in out.sent)
