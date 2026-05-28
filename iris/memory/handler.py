from __future__ import annotations

from threading import Lock
from typing import TYPE_CHECKING, TypedDict

from loguru import logger

from iris.event.event_types import (
    InhibitionAction,
    InhibitionEvent,
    InputReady,
    InterruptEvent,
    MessageEvent,
    TimerTick,
)

if TYPE_CHECKING:
    from typing import Any


class _SystemData(TypedDict, total=False):
    action: str
    user_id: str
    nickname: str
    text: str


class _MemoryEventHandler:
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

        event_bus.subscribe("MessageEvent", self._on_message_event)
        event_bus.subscribe("TimerTick", self._on_timer_tick)

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

    def handle_system_message(self, data: dict, session_id: str, role: str) -> dict | None:
        if self.user_store is None:
            logger.warning("MemoryManager: handle_system_message skipped, no user_store")
            return None

        action = data.get("action", "")
        user_id = data.get("user_id", "")
        nickname = data.get("nickname", "")

        if action == "user_register":
            nickname = nickname or "anonymous"
            uid, nickname = self.user_store.create(nickname)
            logger.info("MemoryManager: registered user_id={} nickname={}", uid, nickname)
            return {"action": "user_register", "user_id": uid, "nickname": nickname, "text": f"Your user ID: {uid}"}

        if action == "user_entered":
            if not user_id:
                return {"action": "user_entered", "text": "Error: user_id required"}
            nickname = self.user_store.resolve(user_id) or user_id
            active = dict(self.short_term.get_active_users() if self.short_term else [])
            is_reconnect = user_id in active
            if self.short_term:
                self.short_term.add_user(user_id, nickname)
            text = (
                f"[system] {nickname} が入室しました" if not is_reconnect else f"[system] {nickname} が再接続しました"
            )
            self._store_and_flush_pending(text, user_id, session_id)
            msg = f"Welcome back, {nickname}" if is_reconnect else f"Welcome, {nickname}"
            return {"action": "user_entered", "user_id": user_id, "nickname": nickname, "text": msg}

        if action == "user_left":
            if not user_id:
                return {"action": "user_left", "text": "Error: user_id required"}
            nickname = self.user_store.resolve(user_id) or user_id
            if self.short_term:
                self.short_term.remove_user(user_id)
            text = f"[system] {nickname} が退室しました"
            self._store_and_flush_pending(text, user_id, session_id)
            if self.event_bus:
                self.event_bus.publish(
                    InhibitionEvent(
                        timestamp=None,
                        source="memory",
                        action=InhibitionAction.UNSUPPRESS,
                        reason="voice_recording",
                    )
                )
            return {"action": "user_left", "user_id": user_id, "text": f"Goodbye, {nickname}"}

        if action == "nickname_update":
            if not user_id or not nickname:
                return {"action": "nickname_update", "text": "Error: user_id and nickname required"}
            self.user_store.set_nickname(user_id, nickname)
            if self.short_term:
                self.short_term.add_user(user_id, nickname)
            text = f"[system] {nickname} に改名しました"
            self._store_and_flush_pending(text, user_id, session_id)
            return {
                "action": "nickname_update",
                "user_id": user_id,
                "nickname": nickname,
                "text": f"Nickname changed to '{nickname}'",
            }

        logger.warning("MemoryManager: unknown system action={}", action)
        return None

    def _store_and_flush_pending(self, text: str, user_id: str, session_id: str) -> None:
        if not self.sensory:
            return
        self.sensory.store_raw(text)
        with self._pending_lock:
            self._pending_input[session_id or ""] = [(text, user_id)]
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
