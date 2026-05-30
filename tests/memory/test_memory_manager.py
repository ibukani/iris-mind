from __future__ import annotations

from typing import Any

import pytest

from iris.event import Event, EventBus
from iris.event.event_types import InputReady, MessageEvent, TimerTick
from iris.memory.handler import _MemoryEventHandler
from iris.memory.manager import MemoryManager


def _message_event(session_id: str = "", content: str = "") -> MessageEvent:
    return MessageEvent(
        timestamp=None,
        source="test",
        session_id=session_id,
        source_role="cli",
        target_role="mind",
        direction="request",
        msg_type="chat",
        content=content,
    )


def _memory_with_handler(event_bus: EventBus, proactive_config: Any = None) -> MemoryManager:
    mgr = MemoryManager()
    _MemoryEventHandler(
        event_bus, mgr.sensory, proactive_config, short_term=mgr.short_term, account_handler=None, room_provider=None
    )
    return mgr


@pytest.fixture
def event_bus() -> EventBus:
    return EventBus()


@pytest.fixture
def memory(event_bus: EventBus) -> MemoryManager:
    return _memory_with_handler(event_bus, {"enabled": True})


def _collect_input_ready(events: list[InputReady]) -> Any:
    def handler(event: Event) -> None:
        events.append(event)

    return handler


class TestMemoryManagerInputPending:
    def test_subscribes_on_init(self, event_bus: EventBus) -> None:
        received: list[MessageEvent] = []

        def handler(event: Event) -> None:
            received.append(event)

        event_bus.subscribe("MessageEvent", handler)
        _memory_with_handler(event_bus)
        event_bus.publish(
            _message_event(session_id="s1", content="hello"),
        )
        assert len(received) == 1
        assert received[0].content == "hello"

    def test_empty_content_ignored(self, event_bus: EventBus) -> None:
        _memory_with_handler(event_bus)
        ready_events: list[InputReady] = []
        event_bus.subscribe("InputReady", _collect_input_ready(ready_events))

        event_bus.publish(
            _message_event(session_id="s1", content=""),
        )
        event_bus.publish(
            TimerTick(timestamp=None, source="kernel", tick_count=0),
        )
        assert len(ready_events) == 0

    def test_message_event_stores_pending(self, event_bus: EventBus) -> None:
        _memory_with_handler(event_bus)

        event_bus.publish(
            _message_event(session_id="s1", content="hello"),
        )
        event_bus.publish(
            _message_event(session_id="s2", content="world"),
        )

        ready_events: list[InputReady] = []
        event_bus.subscribe("InputReady", _collect_input_ready(ready_events))
        event_bus.publish(
            TimerTick(timestamp=None, source="kernel", tick_count=0),
        )

        assert len(ready_events) == 2
        contents = {e.content for e in ready_events}
        assert contents == {"hello", "world"}
        assert all(e.context == {} for e in ready_events)

    def test_timer_with_pending_produces_input_ready(self, event_bus: EventBus, memory: MemoryManager) -> None:
        ready_events: list[InputReady] = []
        event_bus.subscribe("InputReady", _collect_input_ready(ready_events))

        event_bus.publish(
            _message_event(session_id="s1", content="こんにちは"),
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
        _memory_with_handler(event_bus, {"enabled": True})
        event_bus.subscribe("InputReady", _collect_input_ready(ready_events))

        event_bus.publish(
            _message_event(session_id="s1", content="hello"),
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

    def test_multiple_inputs_processed_in_one_tick(self, event_bus: EventBus) -> None:
        ready_events: list[InputReady] = []
        _memory_with_handler(event_bus)
        event_bus.subscribe("InputReady", _collect_input_ready(ready_events))

        event_bus.publish(
            _message_event(session_id="s1", content="first"),
        )
        event_bus.publish(
            _message_event(session_id="s2", content="second"),
        )

        event_bus.publish(
            TimerTick(timestamp=None, source="kernel", tick_count=0),
        )
        assert len(ready_events) == 2
        contents = {e.content for e in ready_events}
        assert contents == {"first", "second"}

        event_bus.publish(
            TimerTick(timestamp=None, source="kernel", tick_count=1),
        )
        # proactive_config が有効ではないので、これ以上イベントは増えないはず
        assert len(ready_events) == 2

    def test_later_input_overwrites_earlier_same_session(self, event_bus: EventBus) -> None:
        ready_events: list[InputReady] = []
        _memory_with_handler(event_bus)
        event_bus.subscribe("InputReady", _collect_input_ready(ready_events))

        event_bus.publish(
            _message_event(session_id="s1", content="old"),
        )
        event_bus.publish(
            _message_event(session_id="s1", content="new"),
        )

        event_bus.publish(
            TimerTick(timestamp=None, source="kernel", tick_count=0),
        )
        assert len(ready_events) == 1
        assert ready_events[0].content == "new"

    def test_proactive_not_triggered_without_config(self, event_bus: EventBus) -> None:
        ready_events: list[InputReady] = []
        _memory_with_handler(event_bus)
        event_bus.subscribe("InputReady", _collect_input_ready(ready_events))

        event_bus.publish(
            TimerTick(timestamp=None, source="kernel", tick_count=0),
        )
        assert len(ready_events) == 0

    def test_user_input_takes_priority_over_proactive(self, event_bus: EventBus) -> None:
        ready_events: list[InputReady] = []
        _memory_with_handler(event_bus)
        event_bus.subscribe("InputReady", _collect_input_ready(ready_events))

        event_bus.publish(
            _message_event(session_id="s1", content="user msg"),
        )
        event_bus.publish(
            TimerTick(timestamp=None, source="kernel", tick_count=0),
        )

        assert len(ready_events) == 1
        assert ready_events[0].content == "user msg"
        assert ready_events[0].context == {}

    def test_timer_removes_published_content(self, event_bus: EventBus) -> None:
        ready_events: list[InputReady] = []
        _memory_with_handler(event_bus)
        event_bus.subscribe("InputReady", _collect_input_ready(ready_events))

        event_bus.publish(
            _message_event(session_id="s1", content="hello"),
        )
        event_bus.publish(
            TimerTick(timestamp=None, source="kernel", tick_count=0),
        )
        assert len(ready_events) == 1

        ready_events.clear()
        event_bus.publish(
            _message_event(session_id="s1", content="second"),
        )
        event_bus.publish(
            TimerTick(timestamp=None, source="kernel", tick_count=1),
        )
        assert len(ready_events) == 1
        assert ready_events[0].content == "second"


class TestInputReadySubscription:
    """_on_input_ready: Gateway → EventBus(InputReady) → Handler の経路。"""

    def test_input_ready_publishes_message_event(self, event_bus: EventBus) -> None:
        _memory_with_handler(event_bus)
        received: list[MessageEvent] = []
        event_bus.subscribe("MessageEvent", lambda e: received.append(e))

        event = InputReady(
            timestamp=None,
            source="io",
            session_id="s1",
            content="hello",
            user_id="",
            context={
                "source_role": "cli",
                "target_role": "mind",
                "msg_type": "chat",
            },
        )
        event_bus.publish(event)

        assert len(received) == 1
        assert received[0].content == "hello"
        assert received[0].session_id == "s1"
        assert received[0].direction == "request"

    def test_input_ready_stores_pending(self, event_bus: EventBus) -> None:
        _memory_with_handler(event_bus)
        flushed_events: list[InputReady] = []
        event_bus.subscribe("InputReady", lambda e: flushed_events.append(e) if e.source == "memory" else None)

        event = InputReady(
            timestamp=None,
            source="io",
            session_id="s1",
            content="テスト",
            user_id="",
            context={
                "source_role": "cli",
                "target_role": "mind",
                "msg_type": "chat",
            },
        )
        event_bus.publish(event)
        event_bus.publish(TimerTick(timestamp=None, source="kernel", tick_count=0))

        assert len(flushed_events) == 1
        assert flushed_events[0].content == "テスト"

    def test_input_ready_voice_indicator(self, event_bus: EventBus) -> None:
        _memory_with_handler(event_bus)
        inhibition_events: list = []
        event_bus.subscribe("InhibitionEvent", lambda e: inhibition_events.append(e))

        event = InputReady(
            timestamp=None,
            source="io",
            session_id="s1",
            content="true",
            user_id="",
            context={
                "source_role": "cli",
                "target_role": "mind",
                "msg_type": "voice_indicator",
            },
        )
        event_bus.publish(event)

        assert len(inhibition_events) == 1
        assert inhibition_events[0].action.value == "suppress"
