from __future__ import annotations

from threading import Lock
from typing import TYPE_CHECKING

from loguru import logger

from iris.event.event_types import (
    InhibitionAction,
    InhibitionEvent,
    InputReady,
    InterruptEvent,
    MessageEvent,
    SessionDisconnectEvent,
    SystemMessageEvent,
    TimerTick,
)
from iris.memory.models import ContentBlock, system_event_block

if TYPE_CHECKING:
    from typing import Any


class _MemoryEventHandler:
    """Memory 層のイベントハンドラ。

    責務:
    - EventBus 上のイベントを購読し、記憶系の処理を行う
    - IO 層からの system メッセージを受信し、EventBus に publish してから処理を行う
    - 処理結果を SystemMessage として返す（IO 層がクライアントに返送）

    設計:
    - 通常メッセージ: Gateway → EventBus.publish(InputReady) → subscribe で受信
    - system メッセージ: Gateway → handler コールバック（同期レスポンス必要）
    - EventBus は memory 層が管理する。
    """

    def __init__(
        self,
        event_bus: Any,
        sensory: Any,
        proactive_config: Any,
        short_term: Any,
        user_store: Any,
    ) -> None:

        self.event_bus = event_bus
        self.sensory = sensory
        self.proactive_config = proactive_config
        self.short_term = short_term
        self.user_store = user_store
        self._pending_input: dict[str, list[tuple[str, str]]] = {}
        self._pending_lock = Lock()

        event_bus.subscribe(InputReady, self._on_input_ready)
        event_bus.subscribe(MessageEvent, self._on_message_event)
        event_bus.subscribe(TimerTick, self._on_timer_tick)
        event_bus.subscribe(SessionDisconnectEvent, self._on_session_disconnect)

    def _on_message_event(self, event: MessageEvent) -> None:
        if event.msg_type == "voice_indicator":
            if event.content == "true":
                self.event_bus.publish(
                    InhibitionEvent(
                        timestamp=None,
                        source="memory",
                        action=InhibitionAction.SUPPRESS,
                        reason="voice_recording",
                    )
                )
            else:
                self.event_bus.publish(
                    InhibitionEvent(
                        timestamp=None,
                        source="memory",
                        action=InhibitionAction.UNSUPPRESS,
                        reason="voice_recording",
                    )
                )
            return

        if not event.content:
            return
        if event.direction not in ("request", "event") or event.msg_type not in ("chat", "system"):
            return
        self.sensory.store_raw(event.content)
        with self._pending_lock:
            self._pending_input[event.session_id] = [(event.content, event.user_identity)]
        logger.debug(
            "MemoryManager: input pending session={} content={:.80} identity={}",
            event.session_id,
            event.content,
            event.user_identity,
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
        self.event_bus.publish(
            MessageEvent(
                timestamp=None,
                source="io",
                session_id=event.session_id,
                source_role=context.get("source_role", ""),
                target_role=context.get("target_role", ""),
                user_identity=event.user_identity,
                direction="request",
                msg_type=context.get("msg_type", "chat"),
                content=event.content,
            )
        )

    def _on_session_disconnect(self, event: SessionDisconnectEvent) -> None:
        if not self.short_term:
            return
        users = self.short_term.get_users_by_session(event.session_id)
        for user_id, nickname in users:
            self.short_term.remove_user(user_id)
            block = system_event_block(
                text=f"[system] {nickname} が退室しました",
                event_type="user_left",
                user_id=user_id,
                nickname=nickname,
            )
            self._store_and_flush_pending_block(block, user_id, event.session_id)
        if self.event_bus:
            self.event_bus.publish(
                InhibitionEvent(
                    timestamp=None,
                    source="memory",
                    action=InhibitionAction.UNSUPPRESS,
                    reason="voice_recording",
                )
            )

    def handle_system_message(self, msg: Any, session_id: str) -> Any:
        """Gateway から呼ばれる system メッセージのエントリポイント。

        受信した SystemMessage を EventBus に publish してから処理を行う。
        これにより、proactive/agency 等の他のレイヤーも system メッセージを
        EventBus 経由で監視できる。
        """
        if self.user_store is None:
            logger.warning("MemoryManager: handle_system_message skipped, no user_store")
            return None

        self.event_bus.publish(
            SystemMessageEvent(
                timestamp=None,
                source="memory",
                action=msg.action,
                user_id=msg.user_id,
                nickname=msg.nickname,
                text=msg.text,
                session_id=session_id,
            )
        )

        action = msg.action
        user_id = msg.user_id
        nickname = msg.nickname

        if action == "user_register":
            nickname = nickname or "anonymous"
            uid, nickname = self.user_store.create(nickname)
            logger.info("MemoryManager: registered user_id={} nickname={}", uid, nickname)
            return SystemMessage(action="user_register", user_id=uid, nickname=nickname, text=f"Your user ID: {uid}")

        if action == "user_entered":
            if not user_id:
                return SystemMessage(action="user_entered", text="Error: user_id required")
            nickname = self.user_store.resolve(user_id) or user_id
            active = dict(self.short_term.get_active_users() if self.short_term else [])
            is_reconnect = user_id in active
            if self.short_term:
                self.short_term.add_user(user_id, nickname, session_id=session_id)
            text = (
                f"[system] {nickname} が入室しました" if not is_reconnect else f"[system] {nickname} が再接続しました"
            )
            event_type = "user_reconnected" if is_reconnect else "user_entered"
            block = system_event_block(text, event_type=event_type, user_id=user_id, nickname=nickname)
            self._store_and_flush_pending_block(block, user_id, session_id)
            reply = f"Welcome back, {nickname}" if is_reconnect else f"Welcome, {nickname}"
            return SystemMessage(action="user_entered", user_id=user_id, nickname=nickname, text=reply)

        if action == "user_left":
            if not user_id:
                return SystemMessage(action="user_left", text="Error: user_id required")
            nickname = self.user_store.resolve(user_id) or user_id
            if self.short_term:
                self.short_term.remove_user(user_id)
            text = f"[system] {nickname} が退室しました"
            block = system_event_block(text, event_type="user_left", user_id=user_id, nickname=nickname)
            self._store_and_flush_pending_block(block, user_id, session_id)
            if self.event_bus:
                self.event_bus.publish(
                    InhibitionEvent(
                        timestamp=None,
                        source="memory",
                        action=InhibitionAction.UNSUPPRESS,
                        reason="voice_recording",
                    )
                )
            return SystemMessage(action="user_left", user_id=user_id, text=f"Goodbye, {nickname}")

        if action == "nickname_update":
            if not user_id or not nickname:
                return SystemMessage(action="nickname_update", text="Error: user_id and nickname required")
            self.user_store.set_nickname(user_id, nickname)
            if self.short_term:
                self.short_term.add_user(user_id, nickname, session_id=session_id)
            text = f"[system] {nickname} に改名しました"
            block = system_event_block(text, event_type="nickname_update", user_id=user_id, nickname=nickname)
            self._store_and_flush_pending_block(block, user_id, session_id)
            return SystemMessage(
                action="nickname_update", user_id=user_id, nickname=nickname, text=f"Nickname changed to '{nickname}'"
            )

        logger.warning("MemoryManager: unknown system action={}", action)
        return None

    def _store_and_flush_pending_block(self, block: ContentBlock, user_id: str, session_id: str) -> None:
        if not self.sensory:
            return
        self.sensory.store_raw_block(block)
        with self._pending_lock:
            self._pending_input[session_id or ""] = [(block.get("text", ""), user_id)]
        self.flush_pending()

    def _on_timer_tick(self, event: TimerTick) -> None:
        if self.event_bus is None:
            return
        pending = self.flush_pending()
        if pending:
            return
        if self.proactive_config is None:
            return
        self.event_bus.publish(
            InputReady(
                timestamp=None,
                source="memory",
                session_id="",
                content="",
                context={"from_timer": True},
            )
        )

    def flush_pending(self) -> dict[str, list[tuple[str, str]]]:
        bus = self.event_bus
        if bus is None:
            return {}
        with self._pending_lock:
            pending = dict(self._pending_input)
            self._pending_input.clear()
        if not pending:
            return {}
        for session_id, entries in pending.items():
            for content, user_identity in entries:
                bus.publish(
                    InterruptEvent(
                        timestamp=None,
                        source="memory",
                        session_id=session_id,
                    )
                )
                bus.publish(
                    InputReady(
                        timestamp=None,
                        source="memory",
                        session_id=session_id,
                        content=content,
                        user_identity=user_identity,
                        context={},
                    )
                )
        return pending
