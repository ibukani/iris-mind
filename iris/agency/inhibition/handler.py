from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

from iris.agency.inhibition.events import InhibitionAction, InhibitionEvent
from iris.io.events import InhibitionRequestEvent

if TYPE_CHECKING:
    from iris.agency.inhibition import InhibitionManager
    from iris.event.event_bus import EventBus


class _InhibitionEventHandler:
    """EventBus経由の外部抑制要請を受け付け、InhibitionManagerに委譲する。

    購読イベント:
      - InhibitionRequestEvent: クライアントからの抑制制御信号（IO 層が型付きに変換済み）
        - action="suppress"   → suppress
        - action="unsuppress" → unsuppress
        - action="hyperdirect"→ 緊急停止
      - InhibitionEvent: 既存の抑制イベント（executor等からの直接発行）
    """

    def __init__(
        self,
        event_bus: EventBus,
        inhibition: InhibitionManager,
    ) -> None:
        self._inhibition = inhibition
        event_bus.subscribe(InhibitionRequestEvent, self._on_request_event)
        event_bus.subscribe(InhibitionEvent, self._on_inhibition_event)

    def _on_request_event(self, event: InhibitionRequestEvent) -> None:
        """型付き InhibitionRequestEvent を InhibitionManager に委譲する。"""
        room_id = event.room_id or None
        action = event.action

        if action in ("suppress", "true", "1"):
            self._inhibition.suppress(event.reason, event.duration, room_id=room_id)
        elif action in ("unsuppress", "false", "0"):
            self._inhibition.unsuppress(event.reason, room_id=room_id)
        elif action == "hyperdirect":
            self._inhibition.suppress("hyperdirect", event.duration, room_id=room_id)
        else:
            logger.warning("Inhibition: unknown action '{}', ignoring", action)

    def _on_inhibition_event(self, event: InhibitionEvent) -> None:
        """InhibitionEvent を InhibitionManager に委譲する。"""
        logger.debug(
            "InhibitionEvent: action={} reason={} duration={} room={}",
            event.action,
            event.reason,
            event.duration,
            event.room_id,
        )
        room_id = event.room_id or None

        if event.action == InhibitionAction.SUPPRESS:
            self._inhibition.suppress(event.reason, event.duration, room_id=room_id)
        elif event.action == InhibitionAction.UNSUPPRESS:
            self._inhibition.unsuppress(event.reason, room_id=room_id)
        elif event.action == InhibitionAction.HYPERDIRECT:
            self._inhibition.suppress("hyperdirect", event.duration)
