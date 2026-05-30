from __future__ import annotations

from typing import TYPE_CHECKING, Any

from loguru import logger

from iris.event.event_types import (
    DebugSnapshotEvent,
    MessageEvent,
    RoomJoinedEvent,
    RoomLeftEvent,
)

if TYPE_CHECKING:
    from iris.account.manager import AccountManager
    from iris.kernel.manager import PluginManager
    from iris.room.manager import RoomManager

    from .orchestrator import LimbicOrchestrator


def subscribe_events(
    manager: PluginManager,
    orchestrator: LimbicOrchestrator,
    account_manager: AccountManager | None = None,
    room_manager: RoomManager | None = None,
) -> None:
    bus = manager.event_bus

    def _on_message(event: MessageEvent) -> None:
        if event.direction != "inbound":
            return
        if not event.content:
            return
        try:
            context: dict[str, Any] = {
                "account_id": event.account_id,
                "room_id": event.room_id,
            }
            user_profile: dict[str, Any] | None = None
            if account_manager and event.account_id:
                account = account_manager.resolve(event.account_id)
                if account:
                    context["display_name"] = account.display_name
                    user_profile = account.profile or None

            if room_manager and event.room_id:
                room = room_manager.get_room(event.room_id)
                if room:
                    context["room_name"] = room.name
                    context["room_topic"] = room.topic

            orchestrator.process(
                event.content,
                context=context,
                user_profile=user_profile,
                account_id=event.account_id,
            )
            _publish_snapshot(bus, orchestrator, "message_processed")
        except Exception:
            logger.exception("Limbic: failed to process message event")

    def _on_room_joined(event: RoomJoinedEvent) -> None:
        try:
            orchestrator.process(
                f"[system] {event.display_name} が入室しました",
                context={
                    "event_type": "room_joined",
                    "display_name": event.display_name,
                    "room_id": event.room_id,
                },
                account_id=event.account_id,
            )
            _publish_snapshot(bus, orchestrator, "room_joined")
        except Exception:
            logger.exception("Limbic: failed to process room_joined event")

    def _on_room_left(event: RoomLeftEvent) -> None:
        try:
            orchestrator.process(
                f"[system] {event.display_name} が退室しました",
                context={
                    "event_type": "room_left",
                    "display_name": event.display_name,
                    "room_id": event.room_id,
                },
                account_id=event.account_id,
            )
            _publish_snapshot(bus, orchestrator, "room_left")
        except Exception:
            logger.exception("Limbic: failed to process room_left event")

    bus.subscribe(MessageEvent, _on_message)
    bus.subscribe(RoomJoinedEvent, _on_room_joined)
    bus.subscribe(RoomLeftEvent, _on_room_left)


def _publish_snapshot(bus: Any, orchestrator: LimbicOrchestrator, trigger: str) -> None:
    try:
        bus.publish(
            DebugSnapshotEvent(
                timestamp=None,
                source="limbic",
                category="limbic",
                data=orchestrator.get_state(),
                trigger=trigger,
            ),
        )
    except Exception:
        logger.debug("Limbic: failed to publish DebugSnapshotEvent")
