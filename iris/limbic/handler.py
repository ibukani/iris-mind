"""Limbic Plugin の EventBus 購読ハンドラ。

`iris/limbic/orchestrator.py` の `LimbicOrchestrator` を `MessageEvent` /
`RoomJoinedEvent` / `RoomLeftEvent` 等のイベントで駆動する。
`LimbicPlugin.init` 時に `_LimbicEventHandler` を構築して bus.subscribe する。
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Any

from loguru import logger

from iris.event.base import DebugSnapshotEvent
from iris.io.events import MessageEvent
from iris.room.events import RoomJoinedBatchEvent, RoomJoinedEvent, RoomLeftEvent

if TYPE_CHECKING:
    from iris.account.manager import AccountManager
    from iris.event.event_bus import EventBus
    from iris.room.manager import RoomManager

    from .orchestrator import LimbicOrchestrator


class _LimbicEventHandler:
    def __init__(
        self,
        event_bus: EventBus,
        orchestrator: LimbicOrchestrator,
        account_manager: AccountManager | None = None,
        room_manager: RoomManager | None = None,
    ) -> None:
        self._bus = event_bus
        self._orchestrator = orchestrator
        self._account_manager = account_manager
        self._room_manager = room_manager

    def subscribe(self) -> None:
        self._bus.subscribe(MessageEvent, self._on_message)
        self._bus.subscribe(RoomJoinedEvent, self._on_room_joined)
        self._bus.subscribe(RoomJoinedBatchEvent, self._on_room_joined_batch)
        self._bus.subscribe(RoomLeftEvent, self._on_room_left)

    def _on_message(self, event: MessageEvent) -> None:
        if event.direction != "request" or not event.content:
            return
        try:
            context: dict[str, Any] = {
                "account_id": event.account_id,
                "room_id": event.room_id,
            }
            user_profile: dict[str, Any] | None = None
            if self._account_manager and event.account_id:
                account = self._account_manager.resolve(event.account_id)
                if account:
                    context["display_name"] = account.display_name
                    user_profile = account.profile or None

            if self._room_manager and event.room_id:
                room = self._room_manager.get_room(event.room_id)
                if room:
                    context["room_name"] = room.name
                    context["room_topic"] = room.topic

            self._orchestrator.process(
                event.content,
                context=context,
                user_profile=user_profile,
                account_id=event.account_id,
            )
            self._publish_snapshot("message_processed")
        except Exception:
            logger.exception("Limbic: failed to process message event")

    def _on_room_joined(self, event: RoomJoinedEvent) -> None:
        try:
            self._orchestrator.process(
                f"[system] {event.display_name} が入室しました",
                context={
                    "event_type": "room_joined",
                    "display_name": event.display_name,
                    "room_id": event.room_id,
                },
                account_id=event.account_id,
            )
            self._publish_snapshot("room_joined")
        except Exception:
            logger.exception("Limbic: failed to process room_joined event")

    def _on_room_joined_batch(self, event: RoomJoinedBatchEvent) -> None:
        try:
            self._publish_snapshot("room_joined_batch")
        except Exception:
            logger.debug("Limbic: failed to publish snapshot for room_joined_batch")

    def _on_room_left(self, event: RoomLeftEvent) -> None:
        try:
            self._orchestrator.process(
                f"[system] {event.display_name} が退室しました",
                context={
                    "event_type": "room_left",
                    "display_name": event.display_name,
                    "room_id": event.room_id,
                },
                account_id=event.account_id,
            )
            self._publish_snapshot("room_left")
        except Exception:
            logger.exception("Limbic: failed to process room_left event")

    def _publish_snapshot(self, trigger: str) -> None:
        with contextlib.suppress(Exception):
            self._bus.publish(
                DebugSnapshotEvent(
                    timestamp=None,
                    source="limbic",
                    category="limbic",
                    data=dict(self._orchestrator.get_state()),
                    trigger=trigger,
                ),
            )


__all__ = ["_LimbicEventHandler"]
