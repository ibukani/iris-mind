from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from loguru import logger

from iris.event.event_types import MessageEvent
from iris.io.models import CommandInput, CommandOutput, Direction, Message

if TYPE_CHECKING:
    from iris.event.event_bus import EventBus
    from iris.io.session.manager import SessionManager


class _IOGateway:
    def __init__(
        self,
        event_bus: EventBus,
        session_manager: SessionManager,
        command_handler: Callable[[str, str], str] | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._session_mgr = session_manager
        self._cmd_handler = command_handler

    def set_command_handler(self, handler: Callable[[str, str], str]) -> None:
        self._cmd_handler = handler

    def on_grpc_message(self, msg: Message) -> None:
        if msg.direction != Direction.REQUEST:
            logger.warning("IOGateway: unexpected direction from client: {}", msg.direction)
            return

        if msg.target_role != "mind":
            self._session_mgr.route_message(msg)
            return

        truncated = msg.content[:200] + "..." if len(msg.content) > 200 else msg.content
        logger.debug(
            "IOGateway: message session={} dir={} type={} source={} target={} content={:.200}",
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
                user_identity=msg.user_identity,
                direction=msg.direction.value,
                msg_type=msg.msg_type,
                content=msg.content,
            )
        )

    def on_grpc_command(self, msg: CommandInput) -> None:
        content = msg.content
        if not content.startswith("/"):
            result = "Commands start with /"
            logger.debug("IOGateway: command missing slash session={}", msg.session_id)
            self._session_mgr.route_command_output(
                msg.session_id,
                CommandOutput(content=result, session_id=msg.session_id, correlation_id=msg.id),
            )
            return

        parts = content[1:].strip().split(maxsplit=1)
        name = parts[0].lower() if parts else ""
        args = parts[1] if len(parts) > 1 else ""

        logger.debug("IOGateway: command session={} cmd=/{} args={:.100}", msg.session_id, name, args)

        result = self._cmd_handler(name, args) if self._cmd_handler else f"No command handler: /{name}"

        logger.debug("IOGateway: command result session={} result={:.100}", msg.session_id, result)
        self._session_mgr.route_command_output(
            msg.session_id,
            CommandOutput(content=result, session_id=msg.session_id, correlation_id=msg.id),
        )
