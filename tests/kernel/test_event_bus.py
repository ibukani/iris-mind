from __future__ import annotations

from iris.event import (
    AgentAnomalyEvent,
    AgentStateChangeEvent,
    Event,
    EventBus,
    MemoryUpdateEvent,
    TimerTick,
)


def test_publish_calls_handler() -> None:
    bus = EventBus()
    received: list[Event] = []

    def handler(event: Event) -> None:
        received.append(event)

    bus.subscribe("TimerTick", handler)
    event = TimerTick(timestamp=None, source="test", tick_count=0)
    bus.publish(event)

    assert len(received) == 1
    assert received[0] is event


def test_multiple_handlers() -> None:
    bus = EventBus()
    results: list[int] = []

    bus.subscribe("TimerTick", lambda _: results.append(1))
    bus.subscribe("TimerTick", lambda _: results.append(2))

    bus.publish(TimerTick(timestamp=None, source="test", tick_count=0))
    assert results == [1, 2]


def test_unsubscribe() -> None:
    bus = EventBus()
    results: list[int] = []

    def handler(_: Event) -> None:
        results.append(1)

    bus.subscribe("AgentAnomalyEvent", handler)
    bus.unsubscribe("AgentAnomalyEvent", handler)
    bus.publish(AgentAnomalyEvent(timestamp=None, source="test", anomaly_type="test", severity="info", detail=""))
    assert results == []


def test_no_handler_for_event_type() -> None:
    bus = EventBus()
    bus.publish(MemoryUpdateEvent(timestamp=None, source="test", entry_type="episodic", content="hi"))
    assert True


def test_handler_error_does_not_affect_others() -> None:
    bus = EventBus()
    results: list[int] = []

    def failing_handler(_: Event) -> None:
        raise ValueError("oops")

    def good_handler(_: Event) -> None:
        results.append(1)

    bus.subscribe("TimerTick", failing_handler)
    bus.subscribe("TimerTick", good_handler)

    bus.publish(TimerTick(timestamp=None, source="test", tick_count=0))
    assert results == [1]


def test_subscribe_registers_handler() -> None:
    bus = EventBus()
    results: list[str] = []

    def handler(_: Event) -> None:
        results.append("called")

    bus.subscribe("AgentStateChangeEvent", handler)
    bus.publish(AgentStateChangeEvent(timestamp=None, source="test", previous_state="idle", new_state="processing"))
    assert results == ["called"]


def test_multiple_event_types() -> None:
    bus = EventBus()
    received: list[str] = []

    bus.subscribe("TimerTick", lambda _: received.append("tick"))
    bus.subscribe("MemoryUpdateEvent", lambda _: received.append("memory"))

    bus.publish(TimerTick(timestamp=None, source="test", tick_count=0))
    bus.publish(MemoryUpdateEvent(timestamp=None, source="test", entry_type="semantic", content="data"))
    assert received == ["tick", "memory"]


def test_publish_with_no_subscribers() -> None:
    bus = EventBus()
    bus.publish(AgentAnomalyEvent(timestamp=None, source="test", anomaly_type="test", severity="info", detail=""))
    assert True


def test_all_event_types_can_be_published() -> None:
    bus = EventBus()
    received: list[str] = []

    def collect(event: Event) -> None:
        received.append(type(event).__name__)

    for name in [
        "TimerTick",
        "AgentStateChangeEvent",
        "MemoryUpdateEvent",
        "AgentAnomalyEvent",
    ]:
        bus.subscribe(name, collect)

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
