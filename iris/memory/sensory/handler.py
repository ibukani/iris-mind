from __future__ import annotations

from typing import Any

from loguru import logger

from iris.event.base import TimerTick
from iris.io.events import InputReady, InterruptEvent, MessageEvent
from iris.memory.models import system_event_block
from iris.memory.sensory.protocol import SensoryMemoryProtocol
from iris.room.events import RoomJoinedBatchEvent, RoomJoinedEvent, RoomLeftEvent


class SensoryEventHandler:
    """感覚記憶 (Sensory Memory) に関連するイベントハンドラ。"""

    def __init__(
        self,
        event_bus: Any,
        sensory: SensoryMemoryProtocol,
    ) -> None:
        self.event_bus = event_bus
        self.sensory = sensory
        if event_bus is not None:
            event_bus.subscribe(MessageEvent, self._on_message_event)
            event_bus.subscribe(RoomJoinedEvent, self._on_room_joined)
            event_bus.subscribe(RoomJoinedBatchEvent, self._on_room_joined_batch)
            event_bus.subscribe(RoomLeftEvent, self._on_room_left)

    def _on_message_event(self, event: MessageEvent) -> None:
        if not event.content:
            return
        if event.direction not in ("request", "event") or event.msg_type not in ("chat", "system"):
            return
        self.sensory.store_raw(
            event.content, account_id=event.account_id, room_id=event.room_id, session_id=event.session_id
        )
        self.sensory.add_pending_input(event.account_id, event.room_id, event.content)
        logger.debug(
            "MemoryManager: input pending account={} content={:.80}",
            event.account_id,
            event.content,
        )

    def _on_timer_tick(self, event: TimerTick) -> bool:
        if self.event_bus is None:
            return False
        processed = False
        active_rooms = self.sensory.get_active_room_ids()
        for room_id in active_rooms:
            raw = self.sensory.take_raw(room_id)
            if raw is not None:
                raw_block = raw.block
                bus = self.event_bus
                bus.publish(
                    InterruptEvent(
                        timestamp=None,
                        source="memory",
                        room_id=raw.room_id,
                    ),
                )
                bus.publish(
                    InputReady(
                        timestamp=None,
                        source="memory",
                        content=raw_block.get("text", "") if raw_block.get("type") == "text" else "",
                        account_id=raw.account_id,
                        room_id=raw.room_id,
                        session_id=raw.session_id,
                        context={},
                    ),
                )
                processed = True
        if processed:
            self.sensory.clear_pending_input()
            return True
        pending = self.sensory.flush_pending()
        return bool(pending)

    def _on_room_joined(self, event: RoomJoinedEvent) -> None:
        self.sensory.store_and_flush_pending_block(
            system_event_block(
                f"[system] {event.display_name} が入室しました",
                event_type="room.joined",
                account_id=event.account_id,
                display_name=event.display_name,
                room_id=event.room_id,
            ),
            event.account_id,
            event.room_id,
        )

    def _on_room_joined_batch(self, event: RoomJoinedBatchEvent) -> None:
        if not event.joins:
            return
        first = event.joins[0]
        join_count = len(event.joins)
        if join_count > 1:
            text = f"[system] {first.display_name} 他{join_count - 1}名が入室しました"
        else:
            text = f"[system] {first.display_name} が入室しました"
        self.sensory.store_and_flush_pending_block(
            system_event_block(
                text,
                event_type="room.joined",
                account_id=first.account_id,
                display_name=first.display_name,
                room_id=first.room_id,
            ),
            first.account_id,
            first.room_id,
        )

    def _on_room_left(self, event: RoomLeftEvent) -> None:
        self.sensory.store_and_flush_pending_block(
            system_event_block(
                f"[system] {event.display_name} が退室しました",
                event_type="room.left",
                account_id=event.account_id,
                display_name=event.display_name,
                room_id=event.room_id,
            ),
            event.account_id,
            event.room_id,
        )
