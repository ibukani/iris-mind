from __future__ import annotations

from typing import Any

import pytest

from iris.event import Event, EventBus
from iris.event.event_types import InputReady, InputReceived, TimerTick
from iris.memory.manager import MemoryManager


@pytest.fixture
def event_bus() -> EventBus:
    return EventBus()


@pytest.fixture
def memory(event_bus: EventBus) -> MemoryManager:
    return MemoryManager(
        event_bus=event_bus,
        proactive_config={"enabled": True},
    )


def _collect_input_ready(events: list[InputReady]) -> Any:
    def handler(event: Event) -> None:
        events.append(event)

    return handler


class TestMemoryManagerInputPending:
    def test_subscribes_on_init(self, event_bus: EventBus) -> None:
        received: list[InputReceived] = []

        def handler(event: Event) -> None:
            received.append(event)

        event_bus.subscribe("InputReceived", handler)
        MemoryManager(event_bus=event_bus)
        event_bus.publish(
            InputReceived(timestamp=None, source="test", session_id="s1", content="hello"),
        )
        assert len(received) == 1
        assert received[0].content == "hello"

    def test_empty_content_ignored(self, event_bus: EventBus) -> None:
        MemoryManager(event_bus=event_bus)
        ready_events: list[InputReady] = []
        event_bus.subscribe("InputReady", _collect_input_ready(ready_events))

        event_bus.publish(
            InputReceived(timestamp=None, source="test", session_id="s1", content=""),
        )
        event_bus.publish(
            TimerTick(timestamp=None, source="kernel", tick_count=0),
        )
        assert len(ready_events) == 0

    def test_input_received_stores_pending(self, event_bus: EventBus) -> None:
        MemoryManager(event_bus=event_bus)

        event_bus.publish(
            InputReceived(timestamp=None, source="test", session_id="s1", content="hello"),
        )
        event_bus.publish(
            InputReceived(timestamp=None, source="test", session_id="s2", content="world"),
        )

        ready_events: list[InputReady] = []
        event_bus.subscribe("InputReady", _collect_input_ready(ready_events))
        event_bus.publish(
            TimerTick(timestamp=None, source="kernel", tick_count=0),
        )

        assert len(ready_events) == 1
        assert ready_events[0].content in ("hello", "world")
        assert ready_events[0].context == {}

    def test_timer_with_pending_produces_input_ready(self, event_bus: EventBus, memory: MemoryManager) -> None:
        ready_events: list[InputReady] = []
        event_bus.subscribe("InputReady", _collect_input_ready(ready_events))

        event_bus.publish(
            InputReceived(timestamp=None, source="test", session_id="s1", content="こんにちは"),
        )
        event_bus.publish(
            TimerTick(timestamp=None, source="kernel", tick_count=0),
        )

        assert len(ready_events) == 1
        assert ready_events[0].content == "こんにちは"
        assert ready_events[0].session_id == "s1"
        assert ready_events[0].context == {}

    def test_timer_without_pending_produces_proactive(self, event_bus: EventBus, memory: MemoryManager) -> None:
        ready_events: list[InputReady] = []
        event_bus.subscribe("InputReady", _collect_input_ready(ready_events))

        event_bus.publish(
            TimerTick(timestamp=None, source="kernel", tick_count=0),
        )

        assert len(ready_events) == 1
        assert ready_events[0].content == ""
        assert ready_events[0].context == {"from_timer": True}

    def test_pending_emptied_after_timer(self, event_bus: EventBus) -> None:
        ready_events: list[InputReady] = []
        MemoryManager(event_bus=event_bus, proactive_config={"enabled": True})
        event_bus.subscribe("InputReady", _collect_input_ready(ready_events))

        event_bus.publish(
            InputReceived(timestamp=None, source="test", session_id="s1", content="hello"),
        )
        event_bus.publish(
            TimerTick(timestamp=None, source="kernel", tick_count=0),
        )
        assert len(ready_events) == 1

        event_bus.publish(
            TimerTick(timestamp=None, source="kernel", tick_count=1),
        )
        assert len(ready_events) == 2
        assert ready_events[1].context == {"from_timer": True}

    def test_multiple_inputs_processed_one_per_tick(self, event_bus: EventBus) -> None:
        ready_events: list[InputReady] = []
        MemoryManager(event_bus=event_bus)
        event_bus.subscribe("InputReady", _collect_input_ready(ready_events))

        event_bus.publish(
            InputReceived(timestamp=None, source="test", session_id="s1", content="first"),
        )
        event_bus.publish(
            InputReceived(timestamp=None, source="test", session_id="s2", content="second"),
        )

        event_bus.publish(
            TimerTick(timestamp=None, source="kernel", tick_count=0),
        )
        assert len(ready_events) == 1
        assert ready_events[0].content in ("first", "second")

        event_bus.publish(
            TimerTick(timestamp=None, source="kernel", tick_count=1),
        )
        assert len(ready_events) == 2
        remaining = {"first", "second"} - {ready_events[0].content}
        assert ready_events[1].content in remaining

    def test_later_input_overwrites_earlier_same_session(self, event_bus: EventBus) -> None:
        ready_events: list[InputReady] = []
        MemoryManager(event_bus=event_bus)
        event_bus.subscribe("InputReady", _collect_input_ready(ready_events))

        event_bus.publish(
            InputReceived(timestamp=None, source="test", session_id="s1", content="old"),
        )
        event_bus.publish(
            InputReceived(timestamp=None, source="test", session_id="s1", content="new"),
        )

        event_bus.publish(
            TimerTick(timestamp=None, source="kernel", tick_count=0),
        )
        assert len(ready_events) == 1
        assert ready_events[0].content == "new"

    def test_proactive_not_triggered_without_config(self, event_bus: EventBus) -> None:
        ready_events: list[InputReady] = []
        MemoryManager(event_bus=event_bus)
        event_bus.subscribe("InputReady", _collect_input_ready(ready_events))

        event_bus.publish(
            TimerTick(timestamp=None, source="kernel", tick_count=0),
        )
        assert len(ready_events) == 0

    def test_user_input_takes_priority_over_proactive(self, event_bus: EventBus) -> None:
        ready_events: list[InputReady] = []
        MemoryManager(event_bus=event_bus)
        event_bus.subscribe("InputReady", _collect_input_ready(ready_events))

        event_bus.publish(
            InputReceived(timestamp=None, source="test", session_id="s1", content="user msg"),
        )
        event_bus.publish(
            TimerTick(timestamp=None, source="kernel", tick_count=0),
        )

        assert len(ready_events) == 1
        assert ready_events[0].content == "user msg"
        assert ready_events[0].context == {}

    def test_timer_removes_published_content(self, event_bus: EventBus) -> None:
        ready_events: list[InputReady] = []
        MemoryManager(event_bus=event_bus)
        event_bus.subscribe("InputReady", _collect_input_ready(ready_events))

        event_bus.publish(
            InputReceived(timestamp=None, source="test", session_id="s1", content="hello"),
        )
        event_bus.publish(
            TimerTick(timestamp=None, source="kernel", tick_count=0),
        )
        assert len(ready_events) == 1

        ready_events.clear()
        event_bus.publish(
            InputReceived(timestamp=None, source="test", session_id="s1", content="second"),
        )
        event_bus.publish(
            TimerTick(timestamp=None, source="kernel", tick_count=1),
        )
        assert len(ready_events) == 1
        assert ready_events[0].content == "second"
