from __future__ import annotations

from typing import Any

from iris.memory.short_term.protocol import ShortTermMemoryProtocol
from iris.room.events import RoomJoinedBatchEvent, RoomJoinedEvent, RoomLeftEvent


class ShortTermEventHandler:
    """短期記憶 (Short Term Memory) に関連するイベントハンドラ。"""

    def __init__(
        self,
        event_bus: Any,
        short_term: ShortTermMemoryProtocol,
    ) -> None:
        self.event_bus = event_bus
        self.short_term = short_term
        if event_bus is not None:
            event_bus.subscribe(RoomJoinedEvent, self._on_room_joined)
            event_bus.subscribe(RoomJoinedBatchEvent, self._on_room_joined_batch)
            event_bus.subscribe(RoomLeftEvent, self._on_room_left)

    def _on_room_joined(self, event: RoomJoinedEvent) -> None:
        self.short_term.add_user(event.account_id, event.display_name, room_id=event.room_id)

    def _on_room_joined_batch(self, event: RoomJoinedBatchEvent) -> None:
        if not event.joins:
            return
        for join in event.joins:
            self.short_term.add_user(join.account_id, join.display_name, room_id=join.room_id)

    def _on_room_left(self, event: RoomLeftEvent) -> None:
        self.short_term.remove_user(event.account_id, room_id=event.room_id)
