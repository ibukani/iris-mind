from __future__ import annotations

import pytest

from iris.memory.models import text_block
from iris.memory.sensory.manager import SensoryMemoryManager

pytestmark = pytest.mark.legacy


class TestSensoryMemoryManager:
    def test_retrieve_keeps_raw_timestamp_stable(self) -> None:
        sensory = SensoryMemoryManager()

        sensory.store_raw("hello", room_id="room-2")
        first = sensory.retrieve(room_id="room-2")
        second = sensory.retrieve(room_id="room-2")

        assert first.raw is not None
        assert second.raw is not None
        assert first.raw.block.get("text") == "hello"
        assert first.room_id == "room-2"
        assert first.raw.timestamp == second.raw.timestamp

    def test_clear_removes_raw_state(self) -> None:
        sensory = SensoryMemoryManager()

        sensory.store_raw_block(text_block("hello"), room_id="room-1")
        assert sensory.has_pending_raw(room_id="room-1") is True

        sensory.clear(room_id="room-1")

        assert sensory.has_pending_raw(room_id="room-1") is False
        snapshot = sensory.retrieve(room_id="room-1")
        assert snapshot.raw is None
        assert snapshot.room_id == "room-1"
