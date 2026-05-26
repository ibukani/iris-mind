from __future__ import annotations

import threading
from typing import Any

from loguru import logger

from iris.event.event_types import InputReady, InterruptEvent


class _MemoryEventHandler:
    def __init__(self, event_bus: Any, sensory: Any, proactive_config: Any) -> None:

        self.event_bus = event_bus
        self.sensory = sensory
        self.proactive_config = proactive_config
        self._pending_input: dict[str, list[tuple[str, str]]] = {}
        self._pending_lock = threading.Lock()

        event_bus.subscribe("MessageEvent", self._on_message_event)
        event_bus.subscribe("TimerTick", self._on_timer_tick)
        event_bus.subscribe("ClientSessionEvent", self._on_client_session_event)

    def _on_message_event(self, event: Any) -> None:
        if not event.content:
            return
        if event.direction not in ("request", "event") or event.msg_type not in ("chat", "system"):
            return
        self.sensory.store_raw(event.content)
        with self._pending_lock:
            self._pending_input.setdefault(event.session_id, []).append((event.content, event.user_identity))
        logger.debug(
            "MemoryManager: input pending session={} content={:.80} identity={}",
            event.session_id,
            event.content,
            event.user_identity,
        )

    def _on_timer_tick(self, event: Any) -> None:
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
                    InputReady(
                        timestamp=None,
                        source="memory",
                        session_id=session_id,
                        content=content,
                        user_identity=user_identity,
                        context={},
                    )
                )
                bus.publish(
                    InterruptEvent(
                        timestamp=None,
                        source="memory",
                        session_id=session_id,
                    )
                )
        return pending

    def _on_client_session_event(self, event: Any) -> None:
        if event.action != "connected":
            return
        if self.event_bus is None:
            return

        logger.info(
            "MemoryManager: client connected session={} role={} offline_duration={}",
            event.session_id,
            event.role,
            event.offline_duration,
        )
        self.event_bus.publish(
            InputReady(
                timestamp=None,
                source="memory",
                session_id=event.session_id,
                content="",
                user_identity=event.identity,
                context={
                    "system_event": event.action,
                    "offline_duration": event.offline_duration,
                    "role": event.role,
                    "identity": event.identity,
                },
            )
        )
