from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

from iris.event.event_types import MessageEvent, RoomJoinedEvent, RoomLeftEvent
from iris.io.models import ControlMessage, Direction, Message

if TYPE_CHECKING:
    from iris.event.event_bus import EventBus
    from iris.io.session.manager import SessionManager
    from iris.kernel.manager import PluginManager
    from iris.room.store import RoomStore


class _IOEventHandler:
    def __init__(
        self, event_bus: EventBus, session_manager: SessionManager, plugin_manager: PluginManager | None = None
    ) -> None:
        self._session_mgr = session_manager
        self._plugin_manager = plugin_manager
        self._room_store_resolved = False
        self._room_store: RoomStore | None = None
        event_bus.subscribe(MessageEvent, self._on_message_event)
        event_bus.subscribe(RoomJoinedEvent, self._on_room_joined)
        event_bus.subscribe(RoomLeftEvent, self._on_room_left)

    def _get_room_store(self) -> None:
        if self._room_store_resolved or self._plugin_manager is None:
            return
        from iris.room.store import RoomStore

        self._room_store = self._plugin_manager.resolve_optional(RoomStore)
        self._room_store_resolved = True

    def _on_message_event(self, event: MessageEvent) -> None:
        direction = event.direction or "response"
        if direction not in ("response", "stream"):
            return

        session_info = self._session_mgr.get_session_info(event.session_id)
        target_role = session_info.role if session_info else event.source_role or "*"

        msg = Message(
            msg_type=event.msg_type,
            content=event.content,
            state=event.state,
            correlation_id=event.correlation_id,
            source_role="mind",
            target_role=target_role,
            session_id=event.session_id,
            account_id=event.account_id,
            direction=Direction(direction),
            room_id=event.room_id,
        )
        if event.room_id:
            msg.metadata["room_id"] = event.room_id
        logger.debug(
            "IOEventHandler: message event session={} type={} state={} target_role={} content_len={}",
            event.session_id,
            event.msg_type,
            event.state,
            target_role,
            len(event.content) if event.content else 0,
        )
        if event.room_id:
            self._get_room_store()
            if self._room_store is not None:
                self._session_mgr.route_to_room(msg, event.room_id, self._room_store)
                return
        self._session_mgr.route_message(msg)

    def _on_room_joined(self, event: RoomJoinedEvent) -> None:
        self._session_mgr.broadcast_control_message(
            ControlMessage(
                action="presence.joined",
                account_id=event.account_id,
                room_id=event.room_id,
                display_name=event.display_name,
            ),
        )

    def _on_room_left(self, event: RoomLeftEvent) -> None:
        self._session_mgr.broadcast_control_message(
            ControlMessage(
                action="presence.left",
                account_id=event.account_id,
                room_id=event.room_id,
                display_name=event.display_name,
            ),
        )
