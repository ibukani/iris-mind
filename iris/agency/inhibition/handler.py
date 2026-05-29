from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

from iris.event.event_types import InhibitionAction, InhibitionEvent

if TYPE_CHECKING:
    from iris.agency.inhibition import InhibitionManager
    from iris.event.event_bus import EventBus


class _InhibitionEventHandler:
    """EventBus経由の外部抑制要請を受け付け、InhibitionManagerに委譲する。

    購読イベント: InhibitionEvent
      - action="suppress"    → inhibition.suppress(reason, duration)
      - action="unsuppress"  → inhibition.unsuppress(reason)
      - action="hyperdirect" → inhibition.suppress("hyperdirect", duration)
    """

    def __init__(
        self,
        event_bus: EventBus,
        inhibition: InhibitionManager,
    ) -> None:
        self._inhibition = inhibition
        event_bus.subscribe(InhibitionEvent, self._on_inhibition_event)

    def _on_inhibition_event(self, event: InhibitionEvent) -> None:
        logger.debug(
            "InhibitionEvent: action={} reason={} duration={}",
            event.action,
            event.reason,
            event.duration,
        )

        if event.action == InhibitionAction.SUPPRESS:
            self._inhibition.suppress(event.reason, event.duration)
        elif event.action == InhibitionAction.UNSUPPRESS:
            self._inhibition.unsuppress(event.reason)
        elif event.action == InhibitionAction.HYPERDIRECT:
            self._inhibition.suppress("hyperdirect", event.duration)
