from __future__ import annotations

from iris.memory.models import text_block
from iris.memory.sensory.manager import SensoryMemoryManager


class TestSensoryMemoryManager:
    def test_retrieve_keeps_raw_timestamp_stable(self) -> None:
        sensory = SensoryMemoryManager(room_id="room-1")

        sensory.store_raw("hello", room_id="room-2")
        first = sensory.retrieve()
        second = sensory.retrieve()

        assert first["raw"] == "hello"
        assert first["room_id"] == "room-2"
        assert first["raw_timestamp"] == second["raw_timestamp"]

    def test_clear_removes_raw_state(self) -> None:
        sensory = SensoryMemoryManager()

        sensory.store_raw_block(text_block("hello"), room_id="room-1")
        assert sensory.has_pending_raw is True

        sensory.clear()

        assert sensory.has_pending_raw is False
        assert sensory.retrieve() == {"room_id": "room-1"}
