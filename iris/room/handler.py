from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from loguru import logger

from iris.event.event_types import SessionDisconnectEvent
from iris.room.events import RoomLeftEvent

if TYPE_CHECKING:
    from iris.event.event_bus import EventBus
    from iris.room.manager import RoomManager
    from iris.room.store import RoomStore


class _RoomEventHandler:
    def __init__(self, event_bus: EventBus, store: RoomStore, room_manager: RoomManager) -> None:
        self._store = store
        self._event_bus = event_bus
        self._room_manager = room_manager
        event_bus.subscribe(SessionDisconnectEvent, self._on_session_disconnect)

    def _on_session_disconnect(self, event: SessionDisconnectEvent) -> None:
        session_id = event.session_id
        logger.debug("RoomEventHandler: session disconnect session_id={}", session_id)
        members = self._store.find_active_members_containing_session(session_id)
        for member in members:
            if session_id in member.session_ids:
                member.session_ids.remove(session_id)

            if not member.session_ids:
                member.disconnected_at = datetime.now(UTC).isoformat()
                self._store.update_member(member)
                if self._event_bus:
                    self._event_bus.publish(
                        RoomLeftEvent(
                            timestamp=datetime.now(UTC),
                            source="room",
                            room_id=member.room_id,
                            account_id=member.account_id,
                            display_name=self._room_manager._resolve_display_name(member.account_id),
                        ),
                    )
                logger.debug(
                    "RoomEventHandler: account {} disconnected from room {} (no remaining sessions)",
                    member.account_id,
                    member.room_id,
                )
            else:
                self._store.update_member(member)
                logger.debug(
                    "RoomEventHandler: removed session {} from account {} ({} sessions remain)",
                    session_id,
                    member.account_id,
                    len(member.session_ids),
                )

        if members:
            logger.debug("RoomEventHandler: processed session disconnect for session={}", session_id)
