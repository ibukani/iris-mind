from __future__ import annotations

from threading import Lock
from typing import Any

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
        account_handler: Any = None,
    ) -> None:

        self.event_bus = event_bus
        self.sensory = sensory
        self.proactive_config = proactive_config
        self.short_term = short_term
        self._account_handler = account_handler
        self._pending_input: dict[str, list[tuple[str, str, str]]] = {}
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
                    ),
                )
            else:
                self.event_bus.publish(
                    InhibitionEvent(
                        timestamp=None,
                        source="memory",
                        action=InhibitionAction.UNSUPPRESS,
                        reason="voice_recording",
                    ),
                )
            return

        if not event.content:
            return
        if event.direction not in ("request", "event") or event.msg_type not in ("chat", "system"):
            return
        self.sensory.store_raw(event.content)
        with self._pending_lock:
            self._pending_input[event.session_id] = [(event.content, event.user_id, event.room_id)]
        logger.debug(
            "MemoryManager: input pending session={} content={:.80} identity={}",
            event.session_id,
            event.content,
            event.user_id,
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
        user_id = event.user_id
        if not user_id and self._account_handler is not None:
            user_id, nickname = self._account_handler.identify_message_speaker(
                event.session_id,
                context.get("speaker"),
            )
            if user_id:
                context["identity"] = user_id
                context["nickname"] = nickname
        self.event_bus.publish(
            MessageEvent(
                timestamp=None,
                source="io",
                session_id=event.session_id,
                source_role=context.get("source_role", ""),
                target_role=context.get("target_role", ""),
                user_id=user_id,
                direction="request",
                msg_type=context.get("msg_type", "chat"),
                content=event.content,
                room_id=event.room_id,
                speaker=context.get("speaker"),
            ),
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
                ),
            )

    def handle_system_message(self, msg: SystemMessageEvent, session_id: str) -> SystemMessageEvent | None:
        """Gateway から呼ばれる system メッセージのエントリポイント。

        受信した SystemMessage を EventBus に publish してから処理を行う。
        これにより、proactive/agency 等の他のレイヤーも system メッセージを
        EventBus 経由で監視できる。
        """
        if self._account_handler is None:
            logger.warning("MemoryManager: handle_system_message skipped, no account_handler")
            return None

        raw_identity = getattr(msg, "identity", None)
        if raw_identity is not None and hasattr(raw_identity, "model_dump"):
            identity = raw_identity.model_dump()
        elif isinstance(raw_identity, dict):
            identity = raw_identity
        else:
            identity = None
        internal_msg = SystemMessageEvent(
            timestamp=None,
            source="memory",
            action=msg.action,
            user_id=msg.user_id,
            account_id=msg.account_id,
            nickname=msg.nickname,
            text=msg.text,
            session_id=session_id,
            identity=identity,
            profile=msg.profile,
        )
        self.event_bus.publish(internal_msg)

        result = self._account_handler.handle_system_message(internal_msg, session_id)

        if result and result.action in ("account.identify", "account.leave", "account.update"):
            action = result.action
            user_id = result.account_id or result.user_id
            nickname = result.nickname

            if action == "account.identify":
                if self.short_term:
                    self.short_term.add_user(user_id, nickname, session_id=session_id)
                text = result.text or f"[system] {nickname} が入室しました"
                block = system_event_block(text, event_type="account.identify", user_id=user_id, nickname=nickname)
                self._store_and_flush_pending_block(block, user_id, session_id)

            elif action == "account.leave":
                if self.short_term:
                    self.short_term.remove_user(user_id)
                text = result.text or f"[system] {nickname} が退室しました"
                block = system_event_block(text, event_type="account.leave", user_id=user_id, nickname=nickname)
                self._store_and_flush_pending_block(block, user_id, session_id)

            elif action == "account.update":
                if self.short_term:
                    self.short_term.add_user(user_id, nickname, session_id=session_id)
                text = result.text or f"[system] {nickname} に改名しました"
                block = system_event_block(text, event_type="account.update", user_id=user_id, nickname=nickname)
                self._store_and_flush_pending_block(block, user_id, session_id)

        return result  # type: ignore[no-any-return]

    def _store_and_flush_pending_block(self, block: ContentBlock, user_id: str, session_id: str) -> None:
        if not self.sensory:
            return
        self.sensory.store_raw_block(block)
        with self._pending_lock:
            self._pending_input[session_id or ""] = [(block.get("text", ""), user_id, "")]
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
            ),
        )

    def flush_pending(self) -> dict[str, list[tuple[str, str, str]]]:
        bus = self.event_bus
        if bus is None:
            return {}
        with self._pending_lock:
            pending = dict(self._pending_input)
            self._pending_input.clear()
        if not pending:
            return {}
        for session_id, entries in pending.items():
            for content, user_id, room_id in entries:
                bus.publish(
                    InterruptEvent(
                        timestamp=None,
                        source="memory",
                        session_id=session_id,
                    ),
                )
                bus.publish(
                    InputReady(
                        timestamp=None,
                        source="memory",
                        session_id=session_id,
                        content=content,
                        user_id=user_id,
                        room_id=room_id,
                        context={},
                    ),
                )
        return pending
