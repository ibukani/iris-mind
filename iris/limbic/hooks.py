from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

from iris.event.event_types import MessageEvent

if TYPE_CHECKING:
    from iris.kernel.manager import PluginManager

    from .orchestrator import LimbicOrchestrator


def subscribe_events(manager: PluginManager, orchestrator: LimbicOrchestrator) -> None:
    bus = manager.event_bus

    def _on_message(event: MessageEvent) -> None:
        if event.direction != "inbound":
            return
        if not event.content:
            return
        try:
            orchestrator.process(
                event.content,
                context={"session_id": event.session_id, "user_id": event.user_id},
            )
        except Exception:
            logger.exception("Limbic: failed to process message event")

    bus.subscribe(MessageEvent, _on_message)
