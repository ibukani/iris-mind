from __future__ import annotations

from datetime import UTC, datetime
import threading
from typing import Any

from iris.event.event_types import RoomJoinedBatchEvent, RoomJoinedEvent


class RoomJoinBatcher:
    """短時間内の連続joinをバッチ処理する。

    指定時間（デフォルト2.5秒）内の同一ルームへのjoinをまとめ、
    RoomJoinedBatchEventとして一度に発行する。
    Event bus への publish は別スレッド（threading.Timer）で行われるため、
    EventBus.publish() がスレッドセーフであることが前提。
    """

    BATCH_WINDOW: float = 2.5

    def __init__(self, event_bus: Any, batch_window: float | None = None) -> None:
        self._event_bus = event_bus
        self._pending: dict[str, list[RoomJoinedEvent]] = {}
        self._timer: threading.Timer | None = None
        self._lock = threading.Lock()
        if batch_window is not None:
            self.BATCH_WINDOW = batch_window

    def add(self, event: RoomJoinedEvent) -> None:
        """joinイベントをバッファに追加する。"""
        with self._lock:
            room_id = event.room_id
            if room_id not in self._pending:
                self._pending[room_id] = []
            self._pending[room_id].append(event)

            if self._timer is None:
                self._timer = threading.Timer(self.BATCH_WINDOW, self._flush)
                self._timer.daemon = True
                self._timer.start()

    def stop(self) -> None:
        """シャットダウン時に残留イベントを即時flushする。"""
        self._flush()

    def _flush(self) -> None:
        """バッファをFlushし、イベントを発行する。"""
        with self._lock:
            pending = dict(self._pending)
            self._pending.clear()
            self._timer = None

        for room_id, events in pending.items():
            if len(events) == 1:
                self._event_bus.publish(events[0])
            else:
                batch = RoomJoinedBatchEvent(
                    timestamp=datetime.now(UTC),
                    source="room",
                    room_id=room_id,
                    joins=events,
                    count=len(events),
                )
                self._event_bus.publish(batch)
