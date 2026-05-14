from __future__ import annotations

from datetime import datetime
from typing import Any

from iris.kernel.event import ProactiveSpeechEvent, UserInputEvent


class _FakeProactive:
    def __init__(self) -> None:
        self.cooldown: float = 0.0
        self.positive_count: int = 0

    def set_cooldown(self, seconds: float) -> None:
        self.cooldown = seconds

    def notify_positive_response(self) -> None:
        self.positive_count += 1


class _FakeEventBus:
    def __init__(self) -> None:
        self.subs: dict[str, Any] = {}

    def subscribe(self, event_type: str, handler: Any) -> None:
        self.subs[event_type] = handler

    def publish(self, event: Any) -> None:
        pass  # not needed for tracker tests

    def unsubscribe(self, event_type: str, handler: Any) -> None:
        pass


def _make_tracker() -> tuple[Any, Any, Any]:
    from iris.kernel.controllers import ProactiveResponseTracker

    proactive = _FakeProactive()
    bus = _FakeEventBus()
    tracker = ProactiveResponseTracker(proactive=proactive, event_bus=bus)
    return tracker, proactive, bus


def test_tracker_sets_cooldown_on_negative_response() -> None:
    tracker, proactive, bus = _make_tracker()

    bus.subs["ProactiveSpeechEvent"](
        ProactiveSpeechEvent(timestamp=datetime(2026, 1, 1), source="test", content="hello", trigger_type="time")
    )
    bus.subs["UserInputEvent"](UserInputEvent(timestamp=datetime(2026, 1, 1), source="test", content="黙れ"))

    assert proactive.cooldown == 600.0
    assert proactive.positive_count == 0


def test_tracker_notifies_positive_on_normal_response() -> None:
    tracker, proactive, bus = _make_tracker()

    bus.subs["ProactiveSpeechEvent"](
        ProactiveSpeechEvent(timestamp=datetime(2026, 1, 1), source="test", content="hello", trigger_type="time")
    )
    bus.subs["UserInputEvent"](UserInputEvent(timestamp=datetime(2026, 1, 1), source="test", content="ありがとう"))

    assert proactive.cooldown == 0.0
    assert proactive.positive_count == 1


def test_tracker_ignores_input_without_proactive() -> None:
    tracker, proactive, bus = _make_tracker()

    bus.subs["UserInputEvent"](UserInputEvent(timestamp=datetime(2026, 1, 1), source="test", content="こんにちは"))

    assert proactive.positive_count == 0
    assert proactive.cooldown == 0.0
