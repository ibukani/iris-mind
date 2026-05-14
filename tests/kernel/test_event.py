from __future__ import annotations

from datetime import datetime

from iris.kernel.event import (
    AgentAnomalyEvent,
    AgentResponseEvent,
    AgentStateChangeEvent,
    AgentStreamEvent,
    Event,
    EventBus,
    EventBusProtocol,
    ProactiveSpeechEvent,
    TimerTick,
    UserInputEvent,
    new_trace_id,
)


def test_all_events_roundtrip_to_dict() -> None:
    events: list[Event] = [
        UserInputEvent(timestamp=datetime(2026, 1, 1), source="test", content="hello"),
        ProactiveSpeechEvent(
            timestamp=datetime(2026, 1, 1), source="test", content="hi", trigger_type="time", confidence=0.8
        ),
        TimerTick(timestamp=datetime(2026, 1, 1), source="test", tick_count=5),
        AgentStateChangeEvent(
            timestamp=datetime(2026, 1, 1), source="test", previous_state="idle", new_state="processing"
        ),
        AgentStreamEvent(timestamp=datetime(2026, 1, 1), source="test", delta="hello ", trace_id="abc"),
        AgentResponseEvent(timestamp=datetime(2026, 1, 1), source="test", content="hello world"),
        AgentAnomalyEvent(
            timestamp=datetime(2026, 1, 1), source="test", anomaly_type="freq", severity="warning", detail="too many"
        ),
    ]
    for original in events:
        data = original.to_dict()
        restored = Event.from_dict(data)
        assert type(restored) is type(original), f"type mismatch for {type(original).__name__}"
        assert restored == original, f"content mismatch for {type(original).__name__}"


def test_to_dict_includes_type_and_trace_id() -> None:
    event = UserInputEvent(timestamp=None, source="cli", content="hello", trace_id="my-trace")
    data = event.to_dict()
    assert data["type"] == "UserInputEvent"
    assert data["trace_id"] == "my-trace"
    assert data["content"] == "hello"


def test_trace_id_auto_assigned_by_eventbus() -> None:
    bus = EventBus()
    received: list[str] = []

    def collector(event: Event) -> None:
        received.append(event.trace_id)

    bus.subscribe("UserInputEvent", collector)
    bus.publish(UserInputEvent(timestamp=None, source="test", content="a"))
    bus.publish(UserInputEvent(timestamp=None, source="test", content="b"))

    assert len(received) == 2
    assert all(tid != "" for tid in received)
    assert received[0] != received[1], "each publish gets a unique trace_id"


def test_trace_id_preserved_when_set() -> None:
    bus = EventBus()
    received: list[Event] = []

    bus.subscribe("UserInputEvent", received.append)
    bus.publish(UserInputEvent(timestamp=None, source="test", content="x", trace_id="custom-id"))

    assert received[0].trace_id == "custom-id"


def test_eventbus_is_protocol() -> None:
    bus = EventBus()
    assert isinstance(bus, EventBusProtocol)


def test_new_trace_id_is_unique() -> None:
    ids = {new_trace_id() for _ in range(100)}
    assert len(ids) == 100
    assert all(isinstance(tid, str) for tid in ids)


def test_unknown_type_raises() -> None:
    import pytest

    with pytest.raises(ValueError, match="Unknown event type"):
        Event.from_dict({"type": "NonExistentEvent", "timestamp": None, "source": "test"})


def test_from_dict_with_missing_optional_field() -> None:
    from iris.kernel.event import UserInputEvent as UIEvent

    data = {"type": "UserInputEvent", "timestamp": None, "source": "test", "content": "hi"}
    restored = Event.from_dict(data)
    assert isinstance(restored, UIEvent)
    assert restored.metadata is None
