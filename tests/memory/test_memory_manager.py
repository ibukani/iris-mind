from __future__ import annotations

from typing import Any

import pytest

from iris.event import Event, EventBus
from iris.event.event_types import InputReady, MessageEvent, TimerTick
from iris.memory.handler import _MemoryEventHandler
from iris.memory.manager import MemoryManager
from iris.memory.short_term.manager import ShortTermMemoryManager
from iris.room.events import RoomJoinedEvent, RoomLeftEvent


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
        event_bus, mgr.sensory, proactive_config, short_term=mgr.short_term, account_dispatcher=None, room_provider=None
    )
    return mgr


def _memory_with_handler_pair(
    event_bus: EventBus, proactive_config: Any = None
) -> tuple[_MemoryEventHandler, MemoryManager]:
    mgr = MemoryManager()
    handler = _MemoryEventHandler(
        event_bus, mgr.sensory, proactive_config, short_term=mgr.short_term, account_dispatcher=None, room_provider=None
    )
    return handler, mgr


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
            account_id="",
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
            account_id="",
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
            account_id="",
            context={
                "source_role": "cli",
                "target_role": "mind",
                "msg_type": "voice_indicator",
            },
        )
        event_bus.publish(event)

        assert len(inhibition_events) == 1
        assert inhibition_events[0].action.value == "suppress"


class TestRoomId:
    def test_message_event_with_room_id_stores_pending(self, event_bus: EventBus) -> None:
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

    def test_store_with_room_id_sets_default(self) -> None:
        mgr = MemoryManager()
        data: dict[str, Any] = {"content": "test"}
        mgr.store("episodic", data, room_id="room1")
        assert data["room_id"] == "room1"

    def test_store_with_room_id_does_not_overwrite(self) -> None:
        mgr = MemoryManager()
        data: dict[str, Any] = {"content": "test", "room_id": "existing"}
        mgr.store("episodic", data, room_id="room1")
        assert data["room_id"] == "existing"

    def test_store_without_room_id_no_key(self) -> None:
        mgr = MemoryManager()
        data: dict[str, Any] = {"content": "test"}
        mgr.store("episodic", data)
        assert "room_id" not in data

    def test_flush_passes_room_id_to_episodic(self) -> None:
        from iris.memory.long_term.manager import LongTermMemoryManager

        class FakeEpisodic:
            def __init__(self) -> None:
                self.stored: list[tuple[str, str]] = []

            def add(self, summary: str, room_id: str = "", account_id: str = "") -> None:
                self.stored.append((summary, room_id))

            def get_recent(self, n: int = 5, room_id: str = "", account_id: str = "") -> list[dict[str, Any]]:
                return []

            def clear(self) -> None:
                pass

            @property
            def max_entries(self) -> int:
                return 30

        fake_ep = FakeEpisodic()
        lt = LongTermMemoryManager(episodic=fake_ep)
        short_term = ShortTermMemoryManager()
        short_term.add_turn("user", [{"type": "text", "text": "hello"}], room_id="room1")

        mgr = MemoryManager(short_term=short_term, long_term=lt)
        mgr.flush(room_id="room1")

        assert len(fake_ep.stored) == 1
        _, stored_room_id = fake_ep.stored[0]
        assert stored_room_id == "room1"

    def test_flush_without_room_id(self) -> None:
        from iris.memory.long_term.manager import LongTermMemoryManager

        class FakeEpisodic:
            def __init__(self) -> None:
                self.stored: list[tuple[str, str]] = []

            def add(self, summary: str, room_id: str = "", account_id: str = "") -> None:
                self.stored.append((summary, room_id))

            def get_recent(self, n: int = 5, room_id: str = "", account_id: str = "") -> list[dict[str, Any]]:
                return []

            def clear(self) -> None:
                pass

            @property
            def max_entries(self) -> int:
                return 30

        fake_ep = FakeEpisodic()
        lt = LongTermMemoryManager(episodic=fake_ep)
        short_term = ShortTermMemoryManager()
        short_term.add_turn("user", [{"type": "text", "text": "hello"}])

        mgr = MemoryManager(short_term=short_term, long_term=lt)
        mgr.flush()

        assert len(fake_ep.stored) == 1
        _, stored_room_id = fake_ep.stored[0]
        assert stored_room_id == ""

    def test_add_episodic_with_room_id(self) -> None:
        from iris.memory.long_term.manager import LongTermMemoryManager

        class FakeEpisodic:
            def __init__(self) -> None:
                self.stored: list[tuple[str, str]] = []

            def add(self, summary: str, room_id: str = "", account_id: str = "") -> None:
                self.stored.append((summary, room_id))

            def get_recent(self, n: int = 5, room_id: str = "", account_id: str = "") -> list[dict[str, Any]]:
                return []

            def clear(self) -> None:
                pass

            @property
            def max_entries(self) -> int:
                return 30

        fake_ep = FakeEpisodic()
        lt = LongTermMemoryManager(episodic=fake_ep)
        mgr = MemoryManager(long_term=lt)
        mgr.add_episodic("test event", kind="conversation", room_id="room2")

        assert len(fake_ep.stored) == 1
        summary, room_id = fake_ep.stored[0]
        assert "conversation" in summary
        assert room_id == "room2"

    def test_add_semantic_with_room_id(self) -> None:
        from iris.memory.long_term.manager import LongTermMemoryManager

        class FakeSemantic:
            def __init__(self) -> None:
                self.stored: list[tuple[dict, str]] = []

            def add(self, data: dict, room_id: str = "", account_id: str = "") -> None:
                self.stored.append((data, room_id))

            def search(self, query: str, max_results: int = 3, account_id: str = "") -> list[dict[str, Any]]:
                return []

            def clear(self) -> None:
                pass

        fake_sem = FakeSemantic()
        lt = LongTermMemoryManager(semantic=fake_sem)
        mgr = MemoryManager(long_term=lt)
        mgr.add_semantic("knowledge", tags=["info"], room_id="room3")

        assert len(fake_sem.stored) == 1
        data, room_id = fake_sem.stored[0]
        assert data["content"] == "knowledge"
        assert room_id == "room3"

    def test_search_semantic_with_room_id_filter(self) -> None:
        from iris.memory.long_term.manager import LongTermMemoryManager

        class FakeSemantic:
            def search(self, query: str, max_results: int = 3, account_id: str = "") -> list[dict[str, Any]]:
                return [
                    {"content": "a", "room_id": "room1", "tags": []},
                    {"content": "b", "room_id": "room2", "tags": []},
                    {"content": "c", "room_id": "room1", "tags": []},
                ]

            def add(self, data: dict, room_id: str = "", account_id: str = "") -> None:
                pass

            def clear(self) -> None:
                pass

        lt = LongTermMemoryManager(semantic=FakeSemantic())
        mgr = MemoryManager(long_term=lt)

        all_results = mgr.search_semantic("query", max_results=10)
        assert len(all_results) == 3

        filtered = mgr.search_semantic("query", max_results=10, room_id="room1")
        assert len(filtered) == 2
        assert all(r["content"] in ("a", "c") for r in filtered)

    def test_get_episodic_recent_with_room_id(self) -> None:
        from iris.memory.long_term.manager import LongTermMemoryManager

        class FakeEpisodic:
            def get_recent(self, n: int = 5, room_id: str = "", account_id: str = "") -> list[dict[str, Any]]:
                if room_id == "room1":
                    return [{"content": "a"}, {"content": "b"}]
                return [{"content": "x"}, {"content": "y"}, {"content": "z"}]

            def add(self, summary: str, room_id: str = "", account_id: str = "") -> None:
                pass

            def clear(self) -> None:
                pass

            @property
            def max_entries(self) -> int:
                return 30

        lt = LongTermMemoryManager(episodic=FakeEpisodic())
        mgr = MemoryManager(long_term=lt)

        all_recent = mgr.get_recent(n=10)
        assert len(all_recent) == 3

        room_recent = mgr.get_recent(n=10, room_id="room1")
        assert len(room_recent) == 2

    def test_short_term_search_with_room_id(self) -> None:
        st = ShortTermMemoryManager()
        st.add_turn("user", [{"type": "text", "text": "hello world"}], room_id="room1")
        st.add_turn("user", [{"type": "text", "text": "goodbye world"}], room_id="room2")

        all_results = st.search("world")
        assert len(all_results) == 2

        room1_results = st.search("world", room_id="room1")
        assert len(room1_results) == 1

    def test_short_term_get_recent_turns_with_room_id(self) -> None:
        st = ShortTermMemoryManager()
        st.add_turn("user", [{"type": "text", "text": "msg1"}], room_id="room1")
        st.add_turn("user", [{"type": "text", "text": "msg2"}], room_id="room2")
        st.add_turn("user", [{"type": "text", "text": "msg3"}], room_id="room1")

        all_turns = st.get_recent_turns(n=10)
        assert len(all_turns) == 3

        room1_turns = st.get_recent_turns(n=10, room_id="room1")
        assert len(room1_turns) == 2

    def test_short_term_get_unconsolidated_with_room_id(self) -> None:
        st = ShortTermMemoryManager()
        st.add_turn("user", [{"type": "text", "text": "msg1"}], room_id="room1")
        st.add_turn("user", [{"type": "text", "text": "msg2"}], room_id="room2")
        st.add_turn("user", [{"type": "text", "text": "msg3"}], room_id="room1")

        all_unconsolidated = st.get_unconsolidated_turns()
        assert len(all_unconsolidated) == 3

        room1_unconsolidated = st.get_unconsolidated_turns(room_id="room1")
        assert len(room1_unconsolidated) == 2

    def test_room_joined_stores_pending(self, event_bus: EventBus) -> None:
        _memory_with_handler(event_bus)

        ready_events: list[InputReady] = []
        event_bus.subscribe("InputReady", _collect_input_ready(ready_events))

        event_bus.publish(
            RoomJoinedEvent(
                timestamp=None,
                source="room",
                account_id="user1",
                display_name="Alice",
                session_id="s1",
                room_id="room1",
            ),
        )

        event_bus.publish(
            TimerTick(timestamp=None, source="kernel", tick_count=0),
        )

        assert len(ready_events) == 1
        assert "入室" in ready_events[0].content

    def test_room_left_stores_pending(self, event_bus: EventBus) -> None:
        _memory_with_handler(event_bus)

        ready_events: list[InputReady] = []
        event_bus.subscribe("InputReady", _collect_input_ready(ready_events))

        event_bus.publish(
            RoomJoinedEvent(
                timestamp=None,
                source="room",
                account_id="user1",
                display_name="Alice",
                session_id="s1",
                room_id="room1",
            ),
        )

        event_bus.publish(
            TimerTick(timestamp=None, source="kernel", tick_count=0),
        )
        ready_events.clear()

        event_bus.publish(
            RoomLeftEvent(
                timestamp=None,
                source="room",
                account_id="user1",
                display_name="Alice",
                session_id="s1",
                room_id="room1",
            ),
        )

        event_bus.publish(
            TimerTick(timestamp=None, source="kernel", tick_count=1),
        )

        assert len(ready_events) == 1
        assert "退室" in ready_events[0].content

    def test_pending_input_tracks_room_id(self, event_bus: EventBus) -> None:
        handler, _ = _memory_with_handler_pair(event_bus)

        event_bus.publish(
            _message_event(session_id="s1", content="hello"),
        )

        with handler._pending_lock:
            assert ("s1", "") in handler._pending_input

    def test_pending_input_room_id_keyed(self, event_bus: EventBus) -> None:
        handler, _ = _memory_with_handler_pair(event_bus)

        event_bus.publish(
            _message_event(session_id="s1", content="msg1"),
        )
        event_bus.publish(
            _message_event(session_id="s2", content="msg2"),
        )

        with handler._pending_lock:
            keys = set(handler._pending_input.keys())
            assert ("s1", "") in keys
            assert ("s2", "") in keys

    def test_handler_user_tracking_add_room(self, event_bus: EventBus) -> None:
        st = ShortTermMemoryManager()
        _MemoryEventHandler(event_bus, None, None, short_term=st, account_dispatcher=None, room_provider=None)

        event_bus.publish(
            RoomJoinedEvent(
                timestamp=None,
                source="room",
                account_id="user1",
                display_name="Alice",
                session_id="s1",
                room_id="room1",
            ),
        )

        users = st.get_users_by_room("room1")
        assert len(users) == 1
        assert users[0] == ("user1", "Alice")

    def test_handler_user_tracking_remove_room(self, event_bus: EventBus) -> None:
        st = ShortTermMemoryManager()
        _MemoryEventHandler(event_bus, None, None, short_term=st, account_dispatcher=None, room_provider=None)

        event_bus.publish(
            RoomJoinedEvent(
                timestamp=None,
                source="room",
                account_id="user1",
                display_name="Alice",
                session_id="s1",
                room_id="room1",
            ),
        )

        event_bus.publish(
            RoomLeftEvent(
                timestamp=None,
                source="room",
                account_id="user1",
                display_name="Alice",
                session_id="s1",
                room_id="room1",
            ),
        )

        users = st.get_users_by_room("room1")
        assert len(users) == 0
