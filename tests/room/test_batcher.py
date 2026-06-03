from __future__ import annotations

import time

import pytest

from iris.event.event_bus import EventBus
from iris.room.batcher import RoomJoinBatcher
from iris.room.events import RoomJoinedBatchEvent, RoomJoinedEvent

pytestmark = pytest.mark.legacy


class TestRoomJoinBatcher:
    def test_single_join_publishes_directly(self) -> None:
        event_bus = EventBus()
        batcher = RoomJoinBatcher(event_bus, batch_window=0.1)
        received: list[object] = []
        event_bus.subscribe(RoomJoinedEvent, lambda e: received.append(e))

        event = RoomJoinedEvent(
            timestamp=None,
            source="room",
            room_id="r1",
            account_id="u1",
            display_name="User1",
        )
        batcher.add(event)
        time.sleep(0.2)

        assert len(received) == 1
        assert isinstance(received[0], RoomJoinedEvent)

    def test_multiple_joins_publishes_batch(self) -> None:
        event_bus = EventBus()
        batcher = RoomJoinBatcher(event_bus, batch_window=0.1)
        received: list[object] = []
        event_bus.subscribe(RoomJoinedBatchEvent, lambda e: received.append(e))

        for i in range(3):
            event = RoomJoinedEvent(
                timestamp=None,
                source="room",
                room_id="r1",
                account_id=f"u{i}",
                display_name=f"User{i}",
            )
            batcher.add(event)
        time.sleep(0.2)

        assert len(received) == 1
        batch = received[0]
        assert isinstance(batch, RoomJoinedBatchEvent)
        assert batch.count == 3
        assert len(batch.joins) == 3
        assert batch.room_id == "r1"

    def test_different_rooms_get_separate_batches(self) -> None:
        event_bus = EventBus()
        batcher = RoomJoinBatcher(event_bus, batch_window=0.1)
        received: list[object] = []
        event_bus.subscribe(RoomJoinedBatchEvent, lambda e: received.append(e))

        for room_id in ["r1", "r2"]:
            for i in range(2):
                event = RoomJoinedEvent(
                    timestamp=None,
                    source="room",
                    room_id=room_id,
                    account_id=f"u{i}",
                    display_name=f"User{i}",
                )
                batcher.add(event)
        time.sleep(0.2)

        assert len(received) == 2
        room_ids = {b.room_id for b in received}
        assert room_ids == {"r1", "r2"}

    def test_batch_event_serialization(self) -> None:
        joins = [
            RoomJoinedEvent(
                timestamp=None,
                source="room",
                room_id="r1",
                account_id="u1",
                display_name="User1",
            ),
            RoomJoinedEvent(
                timestamp=None,
                source="room",
                room_id="r1",
                account_id="u2",
                display_name="User2",
            ),
        ]
        batch = RoomJoinedBatchEvent(
            timestamp=None,
            source="room",
            room_id="r1",
            joins=joins,
            count=2,
        )

        d = batch.model_dump(mode="json")
        assert d["type"] == "RoomJoinedBatchEvent"
        assert d["count"] == 2
        assert len(d["joins"]) == 2

        restored = RoomJoinedBatchEvent.model_validate(d)
        assert isinstance(restored, RoomJoinedBatchEvent)
        assert restored.count == 2
        assert len(restored.joins) == 2
        assert restored.joins[0].account_id == "u1"
