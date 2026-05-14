"""
AgentState — エージェントの状態管理

AgentKernel が所有し、状態遷移の検証とイベント発行を行う。
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from .event.event_bus import AgentStateChangeEvent, EventBus


class State(StrEnum):
    """AgentState の状態一覧。"""

    IDLE = "idle"  # 待機中 — トリガー監視
    PROCESSING = "processing"  # ユーザー入力処理中
    PROACTIVE = "proactive"  # 自発発話実行中
    REFLECTING = "reflecting"  # 自己反省中
    THINKING = "thinking"  # 思考モード (CoT) 推論中
    SLEEPING = "sleeping"  # 一時休止中


# 許可される状態遷移テーブル
_ALLOWED_TRANSITIONS: dict[State, set[State]] = {
    State.IDLE: {State.PROCESSING, State.PROACTIVE, State.SLEEPING, State.THINKING},
    State.PROCESSING: {State.IDLE, State.REFLECTING, State.SLEEPING, State.PROCESSING},
    State.PROACTIVE: {State.IDLE, State.SLEEPING},
    State.REFLECTING: {State.IDLE, State.PROCESSING},
    State.THINKING: {State.IDLE, State.PROCESSING},
    State.SLEEPING: {State.IDLE},
}


@dataclass
class AgentStateManager:
    """
    エージェントの状態を管理する。

    - 状態遷移の検証
    - 遷移時のイベント発行
    - 状態ごとのタイムアウト監視
    """

    event_bus: EventBus
    timeout_seconds: dict[State, float] = field(
        default_factory=lambda: {
            State.PROCESSING: 60.0,
            State.PROACTIVE: 30.0,
            State.REFLECTING: 15.0,
            State.THINKING: 120.0,
        }
    )

    _current: State = field(default=State.IDLE, repr=False)
    _state_start_time: float | None = field(default=None, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    # --- public API ---

    @property
    def current(self) -> State:
        return self._current

    def is_idle(self) -> bool:
        return self._current == State.IDLE

    def is_processing(self) -> bool:
        return self._current == State.PROCESSING

    def is_proactive(self) -> bool:
        return self._current == State.PROACTIVE

    def is_sleeping(self) -> bool:
        return self._current == State.SLEEPING

    def is_thinking(self) -> bool:
        return self._current == State.THINKING

    def is_reflecting(self) -> bool:
        return self._current == State.REFLECTING

    def transition(self, new_state: State) -> bool:
        """
        状態遷移を試行する。

        Returns:
            bool: 遷移が実行されたら True、許可されなければ False。
        """
        with self._lock:
            if new_state == self._current:
                return True  # 同じ状態への遷離は許可

            if not self._is_allowed(self._current, new_state):
                logger.warning("Invalid state transition: %s -> %s", self._current, new_state)
                return False

            previous = self._current
            self._current = new_state
            self._state_start_time = self._import_time()

            self.event_bus.publish(
                AgentStateChangeEvent(
                    timestamp=self._import_datetime(),
                    source="agent_kernel",
                    previous_state=previous.value,
                    new_state=new_state.value,
                )
            )
            return True

    def check_timeout(self) -> State | None:
        """
        現在の状態がタイムアウトしていれば IDLE に遷移する。

        Returns:
            遷移が発生したら State.IDLE、タイムアウトしていなければ None。
        """
        with self._lock:
            if self._state_start_time is None:
                return None

            timeout = self.timeout_seconds.get(self._current)
            if timeout is None:
                return None

            if self._import_time() - self._state_start_time <= timeout:
                return None

            previous = self._current
            self._current = State.IDLE
            self._state_start_time = None

        # Lock released before event publish to avoid deadlock
        self.event_bus.publish(
            AgentStateChangeEvent(
                timestamp=self._import_datetime(),
                source="agent_kernel",
                previous_state=previous.value,
                new_state=State.IDLE.value,
            )
        )
        return State.IDLE

    # --- internal ---

    def _is_allowed(self, from_s: State, to_s: State) -> bool:
        return to_s in _ALLOWED_TRANSITIONS.get(from_s, set())

    @staticmethod
    def _import_time() -> float:
        return time.time()

    @staticmethod
    def _import_datetime() -> datetime:
        return datetime.now()


logger = logging.getLogger(__name__)
