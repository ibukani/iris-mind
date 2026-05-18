from __future__ import annotations

from collections.abc import Callable
import logging

from iris.event.event_bus import EventBus
from iris.event.event_types import InputReceived, OutputRequest
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
        command_handler: Callable[[str, str], str] | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._session_mgr = session_manager
        self._tcp_listener = tcp_listener
        self._cmd_handler = command_handler

        self._event_bus.subscribe("OutputRequest", self._on_output_request)
        self._tcp_listener.set_on_input(self._on_tcp_input)
        self._tcp_listener.set_on_interrupt(self._on_tcp_interrupt)

    def set_command_handler(self, handler: Callable[[str, str], str]) -> None:
        self._cmd_handler = handler

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
        logger.debug(
            "IOManager: output request session=%s type=%s state=%s content_len=%d",
            event.session_id,
            event.message_type,
            event.state,
            len(event.content) if event.content else 0,
        )
        self._session_mgr.route_output(event.session_id, msg)

    def _on_tcp_input(self, msg: InputMessage) -> None:
        truncated = msg.content[:200] + "..." if len(msg.content) > 200 else msg.content
        logger.debug(
            "IOManager: input session=%s type=%s final=%s content=%.200s",
            msg.session_id,
            msg.msg_type,
            msg.is_final,
            truncated,
        )

        if msg.msg_type == "command":
            self._handle_command(msg)
            return

        if msg.msg_type == "converse_text":
            self._session_mgr.route_output(
                msg.session_id,
                OutputMessage(msg_type="ack", content="received"),
            )

        self._event_bus.publish(
            InputReceived(
                timestamp=None,
                source="io",
                session_id=msg.session_id,
                content=msg.content,
                msg_type=msg.msg_type,
                is_final=msg.is_final,
            )
        )

    def _handle_command(self, msg: InputMessage) -> None:
        content = msg.content
        if not content.startswith("/"):
            result = "Commands start with /"
            logger.debug("IOManager: command missing slash session=%s", msg.session_id)
            self._session_mgr.route_output(
                msg.session_id,
                OutputMessage(msg_type="command", content=result),
            )
            return

        parts = content[1:].strip().split(maxsplit=1)
        name = parts[0].lower() if parts else ""
        args = parts[1] if len(parts) > 1 else ""

        logger.debug("IOManager: command session=%s cmd=/%s args=%.100s", msg.session_id, name, args)

        result = self._cmd_handler(name, args) if self._cmd_handler else f"No command handler: /{name}"

        logger.debug("IOManager: command result session=%s result=%.100s", msg.session_id, result)
        self._session_mgr.route_output(
            msg.session_id,
            OutputMessage(msg_type="command", content=result),
        )

    def _on_tcp_interrupt(self, session_id: str) -> None:
        logger.info("IOManager: interrupt received for session=%s", session_id)
        logger.debug("IOManager: interrupt processed session=%s", session_id)
