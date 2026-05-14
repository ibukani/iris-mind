from __future__ import annotations

from iris.kernel.event import (
    AgentAnomalyEvent,
    AgentResponseEvent,
    AgentStateChangeEvent,
    Event,
    EventBus,
    ProactiveSpeechEvent,
    TimerTick,
    UserInputEvent,
)


def test_publish_calls_handler() -> None:
    bus = EventBus()
    received: list[Event] = []

    def handler(event: Event) -> None:
        received.append(event)

    bus.subscribe("UserInputEvent", handler)
    event = UserInputEvent(timestamp=None, source="test", content="hello")
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

    bus.subscribe("AgentResponseEvent", handler)
    bus.unsubscribe("AgentResponseEvent", handler)
    bus.publish(AgentResponseEvent(timestamp=None, source="test", content="hi"))
    assert results == []


def test_no_handler_for_event_type() -> None:
    bus = EventBus()
    bus.publish(UserInputEvent(timestamp=None, source="test", content="hi"))
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

    # Even though failing_handler raised, good_handler was still called
    assert results == [1]


def test_subscribe_registers_handler() -> None:
    bus = EventBus()
    results: list[str] = []

    def handler(_: Event) -> None:
        results.append("called")

    bus.subscribe("TimerTick", handler)
    bus.publish(TimerTick(timestamp=None, source="test", tick_count=0))
    assert results == ["called"]


def test_multiple_event_types() -> None:
    bus = EventBus()
    received: list[str] = []

    bus.subscribe("UserInputEvent", lambda _: received.append("user"))
    bus.subscribe("TimerTick", lambda _: received.append("tick"))

    bus.publish(UserInputEvent(timestamp=None, source="test", content="a"))
    bus.publish(TimerTick(timestamp=None, source="test", tick_count=0))
    assert received == ["user", "tick"]


def test_publish_with_no_subscribers() -> None:
    bus = EventBus()
    bus.publish(AgentStateChangeEvent(timestamp=None, source="test", previous_state=None, new_state=None))
    assert True


def test_all_event_types_can_be_published() -> None:
    bus = EventBus()
    received: list[str] = []

    def collect(event: Event) -> None:
        received.append(type(event).__name__)

    for name in [
        "UserInputEvent",
        "ProactiveSpeechEvent",
        "TimerTick",
        "AgentStateChangeEvent",
        "AgentResponseEvent",
        "AgentAnomalyEvent",
    ]:
        bus.subscribe(name, collect)

    bus.publish(UserInputEvent(timestamp=None, source="t", content=""))
    bus.publish(ProactiveSpeechEvent(timestamp=None, source="t", content="", trigger_type="time", confidence=0.5))
    bus.publish(TimerTick(timestamp=None, source="t", tick_count=0))
    bus.publish(AgentStateChangeEvent(timestamp=None, source="t", previous_state=None, new_state=None))
    bus.publish(AgentResponseEvent(timestamp=None, source="t", content=""))
    bus.publish(AgentAnomalyEvent(timestamp=None, source="t", anomaly_type="test", severity="info", detail=""))

    assert received == [
        "UserInputEvent",
        "ProactiveSpeechEvent",
        "TimerTick",
        "AgentStateChangeEvent",
        "AgentResponseEvent",
        "AgentAnomalyEvent",
    ]
