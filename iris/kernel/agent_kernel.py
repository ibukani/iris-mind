"""
AgentKernel — 状態管理・異常検知・イベント統括

AgentKernel は Iris カーネルのエントリポイント。
ライフサイクル管理（startup/shutdown）、イベントルーティング、
Tier3ガバナンス（異常検知）を担当する。
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from datetime import datetime
from typing import Any

from .agent_state import AgentStateManager, State
from .config import ProactiveConfig
from .event_bus import (
    AgentAnomalyEvent,
    AgentResponseEvent,
    AgentStateChangeEvent,
    EventBus,
    ProactiveSpeechEvent,
    TimerTick,
    UserInputEvent,
)
from .memory_manager import MemoryManager
from .proactive import ProactiveEngine

logger = logging.getLogger(__name__)


class AnomalyDetector:
    """
    Tier3 異常検知エンジン。

    責務:
    - 自発発話の頻度超過検出（直近5分間のスライディングウィンドウ）
    - 抑制状態の悪循環検出（confirmation_mode 頻発など）
    - 異常アラートの生成とレポート
    """

    def __init__(self) -> None:
        self._speech_window: deque[float] = deque()
        self._alert_count: int = 0
        self._max_per_5min: int = 5

    def record_speech(self) -> list[str]:
        """発話を記録し、異常フラグを返す。"""
        now = time.time()
        self._speech_window.append(now)
        while self._speech_window and now - self._speech_window[0] > 300:
            self._speech_window.popleft()

        flags: list[str] = []
        if len(self._speech_window) >= self._max_per_5min:
            flags.append("frequency_exceeded")
            self._alert_count += 1
        return flags

    def check_suppression_health(
        self,
        status: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """抑制状態の健全性をチェックする。"""
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
            issues.append(
                {
                    "type": "negative_mood",
                    "severity": "info",
                    "detail": "Negative mood detected",
                }
            )
        return issues


class AgentKernel:
    """
    Iris カーネル — イベント統括・状態管理・異常検知。

    ライフサイクル:
        kernel = AgentKernel(event_bus, state, proactive, memory, config)
        kernel.startup()
        ...
        kernel.shutdown()

    イベントフロー:
        TimerTick  →（自動配信）→ ProactiveEngine._on_timer_tick
        UserInputEvent → AgentKernel._on_user_input（将来 ConversationService へ）
        ProactiveSpeechEvent → AgentKernel._on_proactive_speech（異常検知＋記憶）
    """

    def __init__(
        self,
        event_bus: EventBus,
        state_manager: AgentStateManager,
        proactive: ProactiveEngine,
        memory: MemoryManager,
        config: ProactiveConfig,
    ) -> None:
        self._event_bus = event_bus
        self._state = state_manager
        self._proactive = proactive
        self._memory = memory
        self._config = config
        self._anomaly = AnomalyDetector()
        self._running = False
        self._timer_thread: threading.Thread | None = None

    # ── ライフサイクル ────────────────────────────────────

    def startup(self) -> None:
        """カーネルを起動する：イベント購読 + タイマースレッド開始。"""
        if self._running:
            logger.warning("AgentKernel already running")
            return
        self._running = True
        self._subscribe_events()
        self._start_timer()
        logger.info("AgentKernel started")

    def shutdown(self) -> None:
        """カーネルを停止する。"""
        self._running = False
        if self._timer_thread is not None:
            self._timer_thread.join(timeout=3)
            self._timer_thread = None
        logger.info("AgentKernel stopped")

    # ── イベント購読 ──────────────────────────────────────

    def _subscribe_events(self) -> None:
        self._event_bus.subscribe("UserInputEvent", self._on_user_input)
        self._event_bus.subscribe("ProactiveSpeechEvent", self._on_proactive_speech)
        self._event_bus.subscribe("AgentStateChangeEvent", self._on_state_change)
        self._event_bus.subscribe("AgentResponseEvent", self._on_agent_response)

    # ── タイマースレッド ──────────────────────────────────

    def _start_timer(self) -> None:
        """TimerTick を定期発行するバックグラウンドスレッド。"""

        def _loop() -> None:
            while self._running:
                try:
                    self._event_bus.publish(
                        TimerTick(
                            timestamp=datetime.now(),
                            source="system",
                            tick_count=0,
                        )
                    )
                    self._state.check_timeout()
                except Exception:
                    logger.exception("TimerTick publish error")
                time.sleep(self._config.check_interval_sec)

        self._timer_thread = threading.Thread(target=_loop, daemon=True, name="agent-kernel-timer")
        self._timer_thread.start()

    # ── イベントハンドラ ──────────────────────────────────

    def _on_user_input(self, event: UserInputEvent) -> None:
        """ユーザー入力イベントを処理する。

        - 状態を PROCESSING に遷移（ConversationService が応答を生成中）
        - ProactiveEngine にユーザー活動を通知
        - 入力をエピソード記憶に記録
        - AgentResponseEvent 到着まで IDLE に戻らない
        """
        if not self._state.is_idle():
            logger.debug("Ignoring input: state=%s", self._state.current)
            return

        self._state.transition(State.PROCESSING)
        self._proactive.notify_user_activity()

        self._memory.add_episodic(
            content=event.content,
            kind="user_input",
            metadata=event.metadata,
        )

    def _on_agent_response(self, event: AgentResponseEvent) -> None:
        """応答イベント受信時に PROCESSING → IDLE に遷移する。"""
        self._memory.add_episodic(
            content=event.content,
            kind="assistant",
            metadata={"model": event.model} if event.model else None,
        )
        if self._state.is_processing():
            self._state.transition(State.IDLE)

    def _on_proactive_speech(self, event: ProactiveSpeechEvent) -> None:
        """自発発話イベントを処理する：記憶記録 + 異常検知。"""
        self._memory.add_episodic(
            content=event.content,
            kind="proactive",
            metadata={
                "trigger": event.trigger_type,
                "confidence": event.confidence,
            },
        )

        anomaly_flags = self._anomaly.record_speech()
        for flag in anomaly_flags:
            logger.warning("Tier3 anomaly: %s", flag)
            self._event_bus.publish(
                AgentAnomalyEvent(
                    timestamp=datetime.now(),
                    source="system",
                    anomaly_type=flag,
                    severity="warning",
                    detail="自発発話の頻度が高すぎます",
                )
            )
            if flag == "frequency_exceeded":
                self._proactive.set_cooldown(300.0)

        health_issues = self._anomaly.check_suppression_health(
            self._proactive.get_status(),
        )
        for issue in health_issues:
            level = logging.WARNING if issue["severity"] == "warning" else logging.INFO
            logger.log(level, "Tier3 health: [%s] %s", issue["type"], issue["detail"])
            self._event_bus.publish(
                AgentAnomalyEvent(
                    timestamp=datetime.now(),
                    source="system",
                    anomaly_type=issue["type"],
                    severity=issue["severity"],
                    detail=issue["detail"],
                )
            )

    @staticmethod
    def _on_state_change(event: AgentStateChangeEvent) -> None:
        """状態変更イベントをログに記録する。"""
        logger.info("State: %s -> %s", event.previous_state, event.new_state)
