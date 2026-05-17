from __future__ import annotations

import logging

from iris.event.event_bus import EventBus
from iris.event.event import InputReceived, OutputRequest
from iris.io.models import InputMessage, OutputMessage
from iris.io.session.manager import SessionManager
from iris.io.transport.tcp_listener import TcpListener

logger = logging.getLogger(__name__)


class IOManager:
    def __init__(
        self,
        event_bus: EventBus,
        session_manager: SessionManager,
        tcp_listener: TcpListener,
    ) -> None:
        self._event_bus = event_bus
        self._session_mgr = session_manager
        self._tcp_listener = tcp_listener

        self._event_bus.subscribe("OutputRequest", self._on_output_request)
        self._tcp_listener.set_on_input(self._on_tcp_input)
        self._tcp_listener.set_on_interrupt(self._on_tcp_interrupt)

    def start(self, host: str, port: int) -> None:
        self._tcp_listener.start(host=host, port=port)

    def stop(self) -> None:
        self._tcp_listener.stop()

    def _on_output_request(self, event: OutputRequest) -> None:
        msg = OutputMessage(
            msg_type=event.message_type,
            content=event.content,
            state=event.state,
            correlation_id=event.correlation_id,
        )
        self._session_mgr.route_output(event.session_id, msg)

    def _on_tcp_input(self, msg: InputMessage) -> None:
        self._event_bus.publish(InputReceived(
            timestamp=None,
            source="io",
            session_id=msg.session_id,
            content=msg.content,
            msg_type=msg.msg_type,
            is_final=msg.is_final,
        ))

    def _on_tcp_interrupt(self, session_id: str) -> None:
        logger.info("IOManager: interrupt received for session=%s", session_id)
