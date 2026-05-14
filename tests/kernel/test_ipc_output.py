from __future__ import annotations

from datetime import datetime
from typing import Any

from iris.kernel.event import (
    AgentAnomalyEvent,
    AgentResponseEvent,
    AgentStreamEvent,
    ProactiveSpeechEvent,
)


class _FakeEventBus:
    def __init__(self) -> None:
        self.subscriptions: dict[str, Any] = {}
        self.unsubscriptions: dict[str, Any] = {}
        self.published: list[Any] = []

    def subscribe(self, event_type: str, handler: Any) -> None:
        self.subscriptions[event_type] = handler

    def unsubscribe(self, event_type: str, handler: Any) -> None:
        self.unsubscriptions[event_type] = handler

    def publish(self, event: Any) -> None:
        self.published.append(event)


def test_output_bridge_subscribes_display_events() -> None:
    from iris.kernel.ipc import OutputBridge

    bus = _FakeEventBus()
    bridge = OutputBridge(bus, r"\\.\pipe\iris-test-unused")  # noqa: P103  // Pipe address for testing

    bridge._subscribe()

    assert "AgentStreamEvent" in bus.subscriptions
    assert "AgentResponseEvent" in bus.subscriptions
    assert "ProactiveSpeechEvent" in bus.subscriptions
    assert "AgentAnomalyEvent" in bus.subscriptions

    bridge._unsubscribe()

    assert "AgentStreamEvent" in bus.unsubscriptions
    assert "AgentResponseEvent" in bus.unsubscriptions
    assert "ProactiveSpeechEvent" in bus.unsubscriptions
    assert "AgentAnomalyEvent" in bus.unsubscriptions


def test_output_bridge_send_handles_no_connection() -> None:
    from iris.kernel.ipc import OutputBridge

    bus = _FakeEventBus()
    bridge = OutputBridge(bus, r"\\.\pipe\iris-test-unused")  # noqa: P103

    # Should not crash when no connection
    bridge._send(AgentStreamEvent(timestamp=datetime(2026, 1, 1), source="assistant", delta="test"))
    bridge._send(
        ProactiveSpeechEvent(timestamp=datetime(2026, 1, 1), source="proactive", content="hi", trigger_type="time")
    )
    bridge._send(AgentResponseEvent(timestamp=datetime(2026, 1, 1), source="assistant", content="ok"))
    bridge._send(
        AgentAnomalyEvent(
            timestamp=datetime(2026, 1, 1), source="system", anomaly_type="test", severity="info", detail="test"
        )
    )
