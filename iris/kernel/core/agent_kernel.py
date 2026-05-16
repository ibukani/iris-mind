from __future__ import annotations

import logging
import threading
import time
from collections import deque
from collections.abc import Callable
from datetime import datetime
from typing import Any

from iris.io.models import InputMessage, OutputMessage
from iris.io.session.manager import SessionManager

from ..agent_state import AgentStateManager, State
from ..config import ProactiveConfig
from iris.event.event_bus import (
    AgentAnomalyEvent,
    AgentStateChangeEvent,
    EventBus,
    TimerTick,
)
from ..services.memory_manager import MemoryManager
from ..services.proactive import ProactiveEngine, ProactiveResult

logger = logging.getLogger(__name__)


class AnomalyDetector:
    def __init__(self, time_provider: Callable[[], float] | None = None, max_per_5min: int = 5) -> None:
        self._time_provider = time_provider or time.time
        self._speech_window: deque[float] = deque()
        self._alert_count: int = 0
        self._max_per_5min = max_per_5min

    def record_speech(self) -> list[str]:
        now = self._time_provider()
        self._speech_window.append(now)
        while self._speech_window and now - self._speech_window[0] > 300:
            self._speech_window.popleft()
        flags: list[str] = []
        if len(self._speech_window) >= self._max_per_5min:
            flags.append("frequency_exceeded")
            self._alert_count += 1
        return flags

    def check_frequency(self) -> list[str]:
        if not self._speech_window:
            return []
        now = self._time_provider()
        count = sum(1 for t in self._speech_window if now - t < 300)
        return ["frequency_exceeded"] if count >= self._max_per_5min else []

    def check_suppression_health(self, status: dict[str, Any]) -> list[dict[str, Any]]:
        issues: list[dict[str, Any]] = []
        s = status.get("suppression", {})
        if s.get("confirmation_mode"):
            issues.append(
                {
                    "type": "confirmation_mode",
                    "severity": "warning",
                    "detail": "User ignoring proactive messages",
                }
            )
        if s.get("consecutive_ignores", 0) >= 3:
            issues.append(
                {
                    "type": "high_ignore_rate",
                    "severity": "warning",
                    "detail": f"Ignores: {s['consecutive_ignores']}",
                }
            )
        if s.get("negative_mood_score", 0.0) >= 0.7:
            issues.append({"type": "negative_mood", "severity": "info", "detail": "Negative mood detected"})
        return issues


class AgentKernel:
    def __init__(
        self,
        event_bus: EventBus,
        state_manager: AgentStateManager,
        proactive: ProactiveEngine,
        memory: MemoryManager,
        config: ProactiveConfig,
        session_manager: SessionManager,
    ) -> None:
        self._event_bus = event_bus
        self._state = state_manager
        self._proactive = proactive
        self._memory = memory
        self._config = config
        self._session_mgr = session_manager
        self._anomaly = AnomalyDetector()
        self._running = False
        self._timer_thread: threading.Thread | None = None

    def startup(self) -> None:
        if self._running:
            logger.warning("AgentKernel already running")
            return
        self._running = True
        self._subscribe_events()
        self._start_timer()
        logger.info("AgentKernel started")

    def shutdown(self) -> None:
        self._running = False
        if self._timer_thread is not None:
            self._timer_thread.join(timeout=3)
            self._timer_thread = None
        logger.info("AgentKernel stopped")

    def _subscribe_events(self) -> None:
        self._event_bus.subscribe("AgentStateChangeEvent", self._on_state_change)

    def _start_timer(self) -> None:
        def _loop() -> None:
            while self._running:
                try:
                    self._event_bus.publish(TimerTick(timestamp=datetime.now(), source="system", tick_count=0))
                    self._state.check_timeout()
                except Exception:
                    logger.exception("TimerTick publish error")
                time.sleep(self._config.check_interval_sec)

        self._timer_thread = threading.Thread(target=_loop, daemon=True, name="agent-kernel-timer")
        self._timer_thread.start()

    def on_input(self, msg: InputMessage) -> None:
        if not self._state.is_idle():
            logger.debug("Ignoring input: state=%s", self._state.current)
            return
        self._state.transition(State.PROCESSING)
        self._proactive.on_user_response(msg.content)
        self._proactive.notify_user_activity()
        self._memory.add_episodic(content=msg.content, kind="user_input", metadata=msg.metadata)

    def on_response_complete(self, content: str, model: str = "") -> None:
        self._memory.add_episodic(content=content, kind="assistant", metadata={"model": model} if model else None)
        if self._state.is_processing():
            self._state.transition(State.IDLE)

    def on_proactive_speech(self, result: ProactiveResult) -> None:
        self._memory.add_episodic(
            content=result.content,
            kind="proactive",
            metadata={"trigger": result.trigger_type, "confidence": result.confidence},
        )
        self._check_and_report_anomalies(result)

    def _check_and_report_anomalies(self, _result: ProactiveResult) -> None:
        anomaly_flags = self._anomaly.record_speech()
        for flag in anomaly_flags:
            logger.warning("Tier3 anomaly: %s", flag)
            ev = AgentAnomalyEvent(
                timestamp=datetime.now(),
                source="system",
                anomaly_type=flag,
                severity="warning",
                detail="自発発話の頻度が高すぎます",
            )
            self._event_bus.publish(ev)
            self._session_mgr.route_output("", OutputMessage(msg_type="error", content=ev.detail))
            if flag == "frequency_exceeded":
                self._proactive.set_cooldown(300.0)

        health_issues = self._anomaly.check_suppression_health(self._proactive.get_status())
        for issue in health_issues:
            level = logging.WARNING if issue["severity"] == "warning" else logging.INFO
            logger.log(level, "Tier3 health: [%s] %s", issue["type"], issue["detail"])
            ev = AgentAnomalyEvent(
                timestamp=datetime.now(),
                source="system",
                anomaly_type=issue["type"],
                severity=issue["severity"],
                detail=issue["detail"],
            )
            self._event_bus.publish(ev)
            if issue["severity"] == "warning":
                self._session_mgr.route_output("", OutputMessage(msg_type="error", content=ev.detail))

    def evaluate_proactive_request(self, _scores: dict[str, float], confidence: float, trigger_type: str) -> bool:
        anomaly_flags = self._anomaly.check_frequency()
        if "frequency_exceeded" in anomaly_flags:
            logger.debug("AgentKernel denied: frequency exceeded")
            return False
        status = self._proactive.get_status()
        health_issues = self._anomaly.check_suppression_health(status)
        if any(i["severity"] == "warning" for i in health_issues):
            logger.debug("AgentKernel denied: suppression issue (%s)", health_issues)
            return False
        if not self._state.is_idle():
            logger.debug("AgentKernel denied: state=%s", self._state.current)
            return False
        logger.debug("AgentKernel approved proactive (confidence=%.2f, trigger=%s)", confidence, trigger_type)
        return True

    @staticmethod
    def _on_state_change(event: AgentStateChangeEvent) -> None:
        logger.info("State: %s -> %s", event.previous_state, event.new_state)
