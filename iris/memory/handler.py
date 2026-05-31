from __future__ import annotations

from threading import Lock
from typing import Any

from loguru import logger

from iris.event.base import TimerTick
from iris.io.events import InputReady, InterruptEvent, MessageEvent
from iris.memory.events import ProactiveTrigger, RoomEventHandler
from iris.memory.models import ContentBlock
from iris.room.events import RoomJoinedBatchEvent, RoomJoinedEvent, RoomLeftEvent


class _MemoryEventHandler:
    """Memory 層のイベントハンドラ。

    責務:
    - EventBus 上のイベントを購読し、記憶系の処理を行う
    - 通常メッセージ: Gateway → EventBus.publish(InputReady) → subscribe で受信
    - Room 参加/退室: RoomEventHandler に委譲
    - TimerTick/プロアクティブ: ProactiveTrigger に委譲

    設計:
    - control メッセージは KernelManager で room.* と account.* に分岐し、
      Memory 層には届かない。Memory 層は Room イベント経由で間接的に処理する。
    - msg_type="inhibition" は InhibitionEventHandler が処理し、Memory 層には届かない。
    """

    def __init__(
        self,
        event_bus: Any,
        sensory: Any,
        proactive_config: Any,
        short_term: Any,
        account_dispatcher: Any = None,
        room_provider: Any = None,
    ) -> None:

        self.event_bus = event_bus
        self.sensory = sensory
        self.proactive_config = proactive_config
        self.short_term = short_term
        self._account_dispatcher = account_dispatcher
        self._room_provider = room_provider
        self._pending_input: dict[tuple[str, str], list[tuple[str, str, str]]] = {}
        self._pending_lock = Lock()

        self._proactive_trigger = ProactiveTrigger(event_bus, room_provider)
        self._room_handler = RoomEventHandler(
            sensory,
            short_term,
            self._store_and_flush_pending_block,
        )

        event_bus.subscribe(InputReady, self._on_input_ready)
        event_bus.subscribe(MessageEvent, self._on_message_event)
        event_bus.subscribe(TimerTick, self._on_timer_tick)
        event_bus.subscribe(RoomJoinedEvent, self._room_handler.handle_joined)
        event_bus.subscribe(RoomJoinedBatchEvent, self._room_handler.handle_joined_batch)
        event_bus.subscribe(RoomLeftEvent, self._room_handler.handle_left)

    def _on_message_event(self, event: MessageEvent) -> None:
        if not event.content:
            return
        if event.direction not in ("request", "event") or event.msg_type not in ("chat", "system"):
            return
        self.sensory.store_raw(
            event.content, account_id=event.account_id, room_id=event.room_id, session_id=event.session_id
        )
        with self._pending_lock:
            self._pending_input[(event.account_id, event.room_id)] = [(event.content, event.account_id, event.room_id)]
        logger.debug(
            "MemoryManager: input pending account={} content={:.80}",
            event.account_id,
            event.content,
        )

    def _on_input_ready(self, event: InputReady) -> None:
        """Gateway からの入力を SensoryMemory に格納する。

        MessageEvent への変換は行わず、SensorMemory に raw として蓄積し、
        TimerTick での一括処理に委ねる。
        source="io" のみ処理。
        """
        if event.source != "io":
            return
        if not event.content:
            return

        self.sensory.store_raw(
            event.content,
            account_id=event.account_id,
            room_id=event.room_id,
            session_id=event.session_id,
        )

    def _store_and_flush_pending_block(
        self,
        block: ContentBlock,
        account_id: str,
        room_id: str = "",
    ) -> None:
        if not self.sensory:
            return
        self.sensory.store_raw_block(block)
        with self._pending_lock:
            self._pending_input[(account_id, room_id)] = [(block.get("text", ""), account_id, room_id)]
        self.flush_pending()
        self.sensory.clear_raw()

    def _on_timer_tick(self, event: TimerTick) -> None:
        if self.event_bus is None:
            return
        raw = self.sensory.take_raw()
        if raw.get("raw"):
            bus = self.event_bus
            bus.publish(
                InterruptEvent(
                    timestamp=None,
                    source="memory",
                    room_id=raw.get("room_id", ""),
                ),
            )
            bus.publish(
                InputReady(
                    timestamp=None,
                    source="memory",
                    content=raw["raw"],
                    account_id=raw.get("account_id", ""),
                    room_id=raw.get("room_id", ""),
                    session_id=raw.get("session_id", ""),
                    context={},
                ),
            )
            with self._pending_lock:
                self._pending_input.clear()
            return
        pending = self.flush_pending()
        if pending:
            return
        if self.proactive_config is None:
            return
        self._proactive_trigger.publish()

    def flush_pending(self) -> dict[tuple[str, str], list[tuple[str, str, str]]]:
        bus = self.event_bus
        if bus is None:
            return {}
        with self._pending_lock:
            pending = dict(self._pending_input)
            self._pending_input.clear()
        if not pending:
            return {}
        for entries in pending.values():
            for content, account_id, room_id in entries:
                bus.publish(
                    InterruptEvent(
                        timestamp=None,
                        source="memory",
                        room_id=room_id,
                    ),
                )
                bus.publish(
                    InputReady(
                        timestamp=None,
                        source="memory",
                        content=content,
                        account_id=account_id,
                        room_id=room_id,
                        context={},
                    ),
                )
        return pending
