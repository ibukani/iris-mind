from __future__ import annotations

from iris.event.base import (
    AgentAnomalyEvent,
    AgentStateChangeEvent,
    Event,
    MemoryUpdateEvent,
    TimerTick,
)
from iris.event.event_bus import EventBus


def test_subscribe_and_publish_delivers_to_handler() -> None:
    bus = EventBus()
    received: list[Event] = []

    def handler(event: TimerTick) -> None:
        received.append(event)

    bus.subscribe(TimerTick, handler)
    bus.subscribe(AgentStateChangeEvent, lambda _: received.append("called"))

    event = TimerTick(timestamp=None, source="test", tick_count=0)
    bus.publish(event)
    bus.publish(AgentStateChangeEvent(timestamp=None, source="test", previous_state="idle", new_state="processing"))

    assert received[0] is event
    assert "called" in received


def test_multiple_handlers() -> None:
    bus = EventBus()
    results: list[int] = []

    bus.subscribe(TimerTick, lambda _: results.append(1))
    bus.subscribe(TimerTick, lambda _: results.append(2))

    bus.publish(TimerTick(timestamp=None, source="test", tick_count=0))
    assert results == [1, 2]


def test_unsubscribe() -> None:
    bus = EventBus()
    results: list[int] = []

    def handler(_: AgentAnomalyEvent) -> None:
        results.append(1)

    bus.subscribe(AgentAnomalyEvent, handler)
    bus.unsubscribe(AgentAnomalyEvent, handler)
    bus.publish(AgentAnomalyEvent(timestamp=None, source="test", anomaly_type="test", severity="info", detail=""))
    assert results == []


def test_publish_with_no_subscribers_is_noop() -> None:
    bus = EventBus()
    bus.publish(MemoryUpdateEvent(timestamp=None, source="test", entry_type="episodic", content="hi"))
    bus.publish(AgentAnomalyEvent(timestamp=None, source="test", anomaly_type="test", severity="info", detail=""))


def test_handler_error_does_not_affect_others() -> None:
    bus = EventBus()
    results: list[int] = []

    def failing_handler(_: TimerTick) -> None:
        raise ValueError("oops")

    def good_handler(_: TimerTick) -> None:
        results.append(1)

    bus.subscribe(TimerTick, failing_handler)
    bus.subscribe(TimerTick, good_handler)

    bus.publish(TimerTick(timestamp=None, source="test", tick_count=0))
    assert results == [1]


def test_multiple_event_types() -> None:
    bus = EventBus()
    received: list[str] = []

    bus.subscribe(TimerTick, lambda _: received.append("tick"))
    bus.subscribe(MemoryUpdateEvent, lambda _: received.append("memory"))

    bus.publish(TimerTick(timestamp=None, source="test", tick_count=0))
    bus.publish(MemoryUpdateEvent(timestamp=None, source="test", entry_type="semantic", content="data"))
    assert received == ["tick", "memory"]


def test_all_event_types_can_be_published() -> None:
    bus = EventBus()
    received: list[str] = []

    def collect(event: Event) -> None:
        received.append(type(event).__name__)

    bus.subscribe(TimerTick, collect)
    bus.subscribe(AgentStateChangeEvent, collect)
    bus.subscribe(MemoryUpdateEvent, collect)
    bus.subscribe(AgentAnomalyEvent, collect)

    bus.publish(TimerTick(timestamp=None, source="t", tick_count=0))
    bus.publish(AgentStateChangeEvent(timestamp=None, source="t", previous_state=None, new_state=None))
    bus.publish(MemoryUpdateEvent(timestamp=None, source="t", entry_type="episodic", content="c"))
    bus.publish(AgentAnomalyEvent(timestamp=None, source="t", anomaly_type="test", severity="info", detail=""))

    assert received == [
        "TimerTick",
        "AgentStateChangeEvent",
        "MemoryUpdateEvent",
        "AgentAnomalyEvent",
    ]
