from __future__ import annotations

from collections.abc import Callable
import logging

from iris.event.event_bus import EventBus
from iris.event.event_types import MessageEvent
from iris.io.models import CommandInput, CommandOutput, Direction, Message
from iris.io.session.manager import SessionManager
from iris.io.transport.grpc_server import GrpcListener

logger = logging.getLogger(__name__)


class IOManager:
    def __init__(
        self,
        event_bus: EventBus,
        session_manager: SessionManager,
        grpc_listener: GrpcListener,
        command_handler: Callable[[str, str], str] | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._session_mgr = session_manager
        self._grpc_listener = grpc_listener
        self._cmd_handler = command_handler

        self._event_bus.subscribe("MessageEvent", self._on_message_event)
        self._grpc_listener.set_on_message(self._on_grpc_message)
        self._grpc_listener.set_on_command(self._on_grpc_command)

    def set_command_handler(self, handler: Callable[[str, str], str]) -> None:
        self._cmd_handler = handler

    def start(self, host: str, port: int) -> None:
        self._grpc_listener.start(host=host, port=port)

    def stop(self) -> None:
        self._grpc_listener.stop()

    def _on_message_event(self, event: MessageEvent) -> None:
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
            direction=Direction(event.direction) if event.direction else Direction.RESPONSE,
        )
        logger.debug(
            "IOManager: message event session=%s type=%s state=%s target_role=%s content_len=%d",
            event.session_id,
            event.msg_type,
            event.state,
            target_role,
            len(event.content) if event.content else 0,
        )
        self._session_mgr.route_message(msg)

    def _on_grpc_message(self, msg: Message) -> None:
        if msg.direction != Direction.REQUEST:
            logger.warning("IOManager: unexpected direction from client: %s", msg.direction)
            return

        if msg.target_role != "mind":
            self._session_mgr.route_message(msg)
            return

        truncated = msg.content[:200] + "..." if len(msg.content) > 200 else msg.content
        logger.debug(
            "IOManager: message session=%s dir=%s type=%s source=%s target=%s content=%.200s",
            msg.session_id,
            msg.direction.value,
            msg.msg_type,
            msg.source_role,
            msg.target_role,
            truncated,
        )

        self._event_bus.publish(
            MessageEvent(
                timestamp=None,
                source="io",
                session_id=msg.session_id,
                source_role=msg.source_role,
                target_role=msg.target_role,
                direction=msg.direction.value,
                msg_type=msg.msg_type,
                content=msg.content,
            )
        )

    def _on_grpc_command(self, msg: CommandInput) -> None:
        content = msg.content
        if not content.startswith("/"):
            result = "Commands start with /"
            logger.debug("IOManager: command missing slash session=%s", msg.session_id)
            self._session_mgr.route_command_output(
                msg.session_id,
                CommandOutput(content=result, session_id=msg.session_id, correlation_id=msg.id),
            )
            return

        parts = content[1:].strip().split(maxsplit=1)
        name = parts[0].lower() if parts else ""
        args = parts[1] if len(parts) > 1 else ""

        logger.debug("IOManager: command session=%s cmd=/%s args=%.100s", msg.session_id, name, args)

        result = self._cmd_handler(name, args) if self._cmd_handler else f"No command handler: /{name}"

        logger.debug("IOManager: command result session=%s result=%.100s", msg.session_id, result)
        self._session_mgr.route_command_output(
            msg.session_id,
            CommandOutput(content=result, session_id=msg.session_id, correlation_id=msg.id),
        )
