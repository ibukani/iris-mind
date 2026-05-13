"""
EventBus — インメモリ同期イベントバス

コンポーネント間のメッセージングを担う。
publish() でイベントを発行し、subscribe() で登録されたハンドラに配信する。
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class Event:
    """イベントの基底クラス。"""

    timestamp: datetime
    source: str  # "user_input" | "proactive" | "system" | "timer"


@dataclass
class UserInputEvent(Event):
    content: str
    metadata: dict[str, Any] | None = None


@dataclass
class ProactiveSpeechEvent(Event):
    content: str
    trigger_type: str  # "temporal" | "memory" | "context_shift"
    confidence: float = 0.0


@dataclass
class TimerTick(Event):
    tick_count: int = 0


@dataclass
class AgentStateChangeEvent(Event):
    previous_state: str
    new_state: str


@dataclass
class MemoryUpdateEvent(Event):
    entry_type: str  # "episodic" | "semantic"
    content: str


@dataclass
class AgentResponseEvent(Event):
    """会話応答イベント。ConversationService が LLM 応答を発行する。"""
    content: str
    model: str = ""


@dataclass
class AgentAnomalyEvent(Event):
    """Tier3 異常検知イベント。AgentKernel が検出した異常を通知する。"""
    anomaly_type: str  # "frequency_exceeded" | "confirmation_mode" | "high_ignore_rate"
    severity: str  # "warning" | "info"
    detail: str


class EventBus:
    """
    同期インメモリEventBus。

    使い方:
        bus = EventBus()
        bus.subscribe("UserInputEvent", on_user_input)
        bus.publish(UserInputEvent(...))
    """

    def __init__(self) -> None:
        self._subscribers: dict[str, list[Callable]] = defaultdict(list)

    def publish(self, event: Event) -> None:
        """イベントを発行する。該当するハンドラにすべて配信する。"""
        event_type = type(event).__name__
        for handler in self._subscribers.get(event_type, []):
            try:
                handler(event)
            except Exception:
                # 個別ハンドラの例外はログに出すが、他のハンドラの実行を妨げない
                import logging

                logging.getLogger(__name__).exception(
                    "EventBus handler error in %s for %s",
                    handler.__qualname__,
                    event_type,
                )

    def subscribe(self, event_type: str, handler: Callable) -> None:
        """指定イベントタイプのハンドラを登録する。"""
        self._subscribers[event_type].append(handler)

    def unsubscribe(self, event_type: str, handler: Callable) -> None:
        """指定イベントタイプのハンドラを解除する。"""
        with suppress(ValueError):
            self._subscribers[event_type].remove(handler)
