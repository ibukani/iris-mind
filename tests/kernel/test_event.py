from __future__ import annotations

from datetime import datetime

import pytest

from iris.event import (
    AgentAnomalyEvent,
    AgentStateChangeEvent,
    Event,
    MemoryUpdateEvent,
    TimerTick,
    new_trace_id,
)


def test_event_roundtrip_to_dict_and_back() -> None:
    events: list[Event] = [
        TimerTick(timestamp=datetime(2026, 1, 1), source="kernel", tick_count=3),
        TimerTick(timestamp=None, source="kernel", tick_count=0),
        AgentStateChangeEvent(
            timestamp=datetime(2026, 1, 1),
            source="kernel",
            previous_state="idle",
            new_state="processing",
        ),
        MemoryUpdateEvent(
            timestamp=datetime(2026, 1, 1),
            source="memory",
            entry_type="episodic",
            content="user said hello",
        ),
        AgentAnomalyEvent(
            timestamp=datetime(2026, 1, 1),
            source="kernel",
            anomaly_type="frequency",
            severity="warning",
            detail="too many retries",
        ),
    ]
    for original in events:
        data = original.to_dict()
        restored = Event.from_dict(data)
        assert type(restored) is type(original), f"type mismatch for {type(original).__name__}"
        assert restored == original, f"content mismatch for {type(original).__name__}"


def test_to_dict_includes_type_and_all_fields() -> None:
    event = AgentAnomalyEvent(
        timestamp=None,
        source="test",
        anomaly_type="latency",
        severity="critical",
        detail="timeout",
    )
    data = event.to_dict()
    assert data["type"] == "AgentAnomalyEvent"
    assert data["source"] == "test"
    assert data["anomaly_type"] == "latency"
    assert data["severity"] == "critical"
    assert data["detail"] == "timeout"


def test_from_dict_resolves_correct_type() -> None:
    data = {
        "type": "AgentStateChangeEvent",
        "timestamp": None,
        "source": "kernel",
        "previous_state": "idle",
        "new_state": "processing",
    }
    restored = Event.from_dict(data)
    assert isinstance(restored, AgentStateChangeEvent)
    assert restored.previous_state == "idle"
    assert restored.new_state == "processing"


def test_new_trace_id_generates_non_empty_strings() -> None:
    ids = {new_trace_id() for _ in range(100)}
    assert len(ids) == 100
    assert all(isinstance(tid, str) and len(tid) > 0 for tid in ids)


def test_unknown_event_type_raises_value_error() -> None:
    with pytest.raises(ValueError, match="Unknown event type"):
        Event.from_dict({"type": "NonExistentEvent", "timestamp": None, "source": "test"})


def test_trace_id_roundtrips_through_from_dict() -> None:
    event = TimerTick(timestamp=None, source="test", tick_count=1, trace_id="custom-trace")
    data = event.to_dict()
    restored = Event.from_dict(data)
    assert restored.trace_id == "custom-trace"
