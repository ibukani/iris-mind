from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from loguru import logger

from iris.account.models import Provider
from iris.event.event_types import MessageEvent, SessionDisconnectEvent
from iris.room.events import RoomLeftEvent

if TYPE_CHECKING:
    from iris.event.event_bus import EventBus
    from iris.room.manager import RoomManager
    from iris.room.store import RoomStore


class _RoomEventHandler:
    def __init__(
        self,
        event_bus: EventBus,
        store: RoomStore,
        room_manager: RoomManager,
        account_manager: Any | None = None,
    ) -> None:
        self._store = store
        self._event_bus = event_bus
        self._room_manager = room_manager
        self._account_manager = account_manager
        event_bus.subscribe(SessionDisconnectEvent, self._on_session_disconnect)
        event_bus.subscribe(MessageEvent, self._on_message_event)

    def _on_message_event(self, event: MessageEvent) -> None:
        if event.direction not in ("request", "event"):
            return
        if event.msg_type not in ("chat", "system"):
            return
        if not event.room_id:
            return

        account_id = event.account_id or self._resolve_account(event)
        if not account_id:
            return

        if not event.account_id:
            event.account_id = account_id

        self._room_manager.join_room(
            event.room_id,
            account_id,
            session_id=event.session_id,
        )

    def _resolve_account(self, event: MessageEvent) -> str:
        if not self._account_manager or not event.speaker:
            return ""
        speaker = event.speaker
        provider_raw = getattr(speaker, "provider", "")
        subject = getattr(speaker, "subject", "")
        if not provider_raw or not subject:
            return ""
        try:
            provider = Provider(provider_raw)
        except ValueError:
            logger.warning("RoomEventHandler: unknown provider={}", provider_raw)
            return ""
        account = self._account_manager.resolve_or_create_identity(
            provider,
            subject,
            provider_name=getattr(speaker, "provider_name", ""),
            metadata=dict(getattr(speaker, "metadata", {})) if hasattr(speaker, "metadata") else None,
        )
        return str(account.account_id)

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
