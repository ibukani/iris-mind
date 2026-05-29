from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

from iris.event.event_types import MessageEvent
from iris.io.models import Direction, Message

if TYPE_CHECKING:
    from iris.event.event_bus import EventBus
    from iris.io.session.manager import SessionManager


class _IOEventHandler:
    def __init__(self, event_bus: EventBus, session_manager: SessionManager) -> None:
        self._session_mgr = session_manager
        event_bus.subscribe(MessageEvent, self._on_message_event)

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
            user_identity=event.user_identity,
            direction=Direction(direction),
        )
        logger.debug(
            "IOEventHandler: message event session={} type={} state={} target_role={} content_len={}",
            event.session_id,
            event.msg_type,
            event.state,
            target_role,
            len(event.content) if event.content else 0,
        )
        self._session_mgr.route_message(msg)
