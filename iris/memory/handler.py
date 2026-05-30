from __future__ import annotations

from threading import Lock
from typing import Any

from loguru import logger

from iris.event.event_types import (
    Identity,
    InhibitionAction,
    InhibitionEvent,
    InputReady,
    InterruptEvent,
    MessageEvent,
    TimerTick,
)
from iris.memory.models import ContentBlock, system_event_block
from iris.room.events import RoomJoinedEvent, RoomLeftEvent


class _MemoryEventHandler:
    """Memory 層のイベントハンドラ。

    責務:
    - EventBus 上のイベントを購読し、記憶系の処理を行う
    - 通常メッセージ: Gateway → EventBus.publish(InputReady) → subscribe で受信
    - Room 参加/退室: RoomJoinedEvent/RoomLeftEvent → ユーザー追跡 + system_event_block

    設計:
    - control メッセージは KernelManager で room.* と account.* に分岐し、
      Memory 層には届かない。Memory 層は Room イベント経由で間接的に処理する。
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

        event_bus.subscribe(InputReady, self._on_input_ready)
        event_bus.subscribe(MessageEvent, self._on_message_event)
        event_bus.subscribe(TimerTick, self._on_timer_tick)
        event_bus.subscribe(RoomJoinedEvent, self._on_room_joined)
        event_bus.subscribe(RoomLeftEvent, self._on_room_left)

    def _on_message_event(self, event: MessageEvent) -> None:
        if event.msg_type == "voice_indicator":
            if event.content == "true":
                self.event_bus.publish(
                    InhibitionEvent(
                        timestamp=None,
                        source="memory",
                        action=InhibitionAction.SUPPRESS,
                        reason="voice_recording",
                        room_id=event.room_id,
                    ),
                )
            else:
                self.event_bus.publish(
                    InhibitionEvent(
                        timestamp=None,
                        source="memory",
                        action=InhibitionAction.UNSUPPRESS,
                        reason="voice_recording",
                        room_id=event.room_id,
                    ),
                )
            return

        if not event.content:
            return
        if event.direction not in ("request", "event") or event.msg_type not in ("chat", "system"):
            return
        self.sensory.store_raw(event.content)
        with self._pending_lock:
            self._pending_input[(event.account_id, event.room_id)] = [(event.content, event.account_id, event.room_id)]
        logger.debug(
            "MemoryManager: input pending account={} content={:.80}",
            event.account_id,
            event.content,
        )

    def _on_input_ready(self, event: InputReady) -> None:
        """Gateway から EventBus 経由で受信した通常メッセージを処理する。

        InputReady イベントを MessageEvent に変換して EventBus に publish し、
        _on_message_event（記憶処理）および io/handler（レスポンス・ストリームのルーティング）を動作させる。
        source="io" のみ処理。source="memory"（flush_pending からの発行）は無視してループ防止。
        """
        if event.source != "io":
            return
        if not event.content:
            return

        context = event.context or {}
        raw_speaker = context.get("speaker")
        speaker = Identity(**raw_speaker) if isinstance(raw_speaker, dict) else None
        self.event_bus.publish(
            MessageEvent(
                timestamp=None,
                source="io",
                session_id=event.session_id,
                source_role=context.get("source_role", ""),
                target_role=context.get("target_role", ""),
                account_id=event.account_id,
                direction="request",
                msg_type=context.get("msg_type", "chat"),
                content=event.content,
                room_id=event.room_id,
                speaker=speaker,
            ),
        )

    def _on_room_joined(self, event: RoomJoinedEvent) -> None:
        """Room参加時にユーザーを追跡し、system_event_blockを生成する。"""
        if self.short_term:
            self.short_term.add_user(event.account_id, event.display_name, room_id=event.room_id)
        text = f"[system] {event.display_name} が入室しました"
        block = system_event_block(
            text,
            event_type="room.joined",
            account_id=event.account_id,
            display_name=event.display_name,
            room_id=event.room_id,
        )
        self._store_and_flush_pending_block(block, event.account_id, event.room_id)

    def _on_room_left(self, event: RoomLeftEvent) -> None:
        """Room退室時にユーザー追跡を解除する。"""
        if self.short_term:
            self.short_term.remove_user(event.account_id, room_id=event.room_id)
        text = f"[system] {event.display_name} が退室しました"
        block = system_event_block(
            text,
            event_type="room.left",
            account_id=event.account_id,
            display_name=event.display_name,
            room_id=event.room_id,
        )
        self._store_and_flush_pending_block(block, event.account_id, event.room_id)

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

    def _on_timer_tick(self, event: TimerTick) -> None:
        if self.event_bus is None:
            return
        pending = self.flush_pending()
        if pending:
            return
        if self.proactive_config is None:
            return
        room_id = self._select_proactive_room()
        self.event_bus.publish(
            InputReady(
                timestamp=None,
                source="memory",
                session_id="",
                room_id=room_id,
                content="",
                context={"from_timer": True},
            ),
        )

    def _select_proactive_room(self) -> str:
        if not self._room_provider:
            return ""
        rooms = self._room_provider.list_rooms()
        if not rooms:
            default = self._room_provider.get_default_room()
            return default.room_id if default else ""
        best_room = None
        best_active = None
        for room in rooms:
            members = self._room_provider.get_members(room.room_id)
            for m in members:
                if m.is_active and (best_active is None or (m.last_active or "") > (best_active or "")):
                    best_active = m.last_active
                    best_room = room
        if best_room:
            return str(best_room.room_id)
        default = self._room_provider.get_default_room()
        return default.room_id if default else ""

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
