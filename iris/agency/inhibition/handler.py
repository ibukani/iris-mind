from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

from iris.agency.inhibition.events import InhibitionAction, InhibitionEvent
from iris.io.events import MessageEvent

if TYPE_CHECKING:
    from iris.agency.inhibition import InhibitionManager
    from iris.event.event_bus import EventBus


class _InhibitionEventHandler:
    """EventBus経由の外部抑制要請を受け付け、InhibitionManagerに委譲する。

    購読イベント:
      - MessageEvent (msg_type="inhibition"): クライアントからの抑制制御信号
        content フォーマット: "reason:action[:duration]"
          - "voice_recording:true"       → suppress
          - "voice_recording:false"      → unsuppress
          - "speaking:true:30.0"         → suppress（30秒間）
          - "hyperdirect:true"           → 緊急停止
      - InhibitionEvent: 既存の抑制イベント（executor等からの直接発行）
    """

    def __init__(
        self,
        event_bus: EventBus,
        inhibition: InhibitionManager,
    ) -> None:
        self._inhibition = inhibition
        event_bus.subscribe(MessageEvent, self._on_message_event)
        event_bus.subscribe(InhibitionEvent, self._on_inhibition_event)

    def _on_message_event(self, event: MessageEvent) -> None:
        """msg_type="inhibition" の MessageEvent を InhibitionEvent に変換する。"""
        if event.msg_type != "inhibition":
            return

        content = event.content
        parts = content.split(":")
        if len(parts) < 2:
            logger.warning(
                "Inhibition: invalid content format '{}', expected 'reason:action[:duration]'",
                content,
            )
            return

        reason = parts[0]
        activate = parts[1] == "true"

        duration = 0.0
        if len(parts) >= 3:
            try:
                duration = float(parts[2])
            except ValueError:
                logger.warning("Inhibition: invalid duration '{}', ignoring", parts[2])
                return

        room_id = event.room_id or None
        if activate:
            self._inhibition.suppress(reason, duration, room_id=room_id)
        else:
            self._inhibition.unsuppress(reason, room_id=room_id)

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
