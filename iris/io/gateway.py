from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from loguru import logger

from iris.event.event_types import InputReady
from iris.io.models import CommandInput, CommandOutput, Direction, Message, SystemMessage

if TYPE_CHECKING:
    from iris.io.session.manager import SessionManager


class _IOGateway:
    """IO層のアダプタ。gRPC と内部レイヤーの橋渡しを行う。

    責務:
    - gRPC メッセージを内部表現に変換し、EventBus に publish する
    - command メッセージは直接コールバックで処理（同期レスポンス必要）
    - system メッセージは直接コールバックで処理（同期レスポンス必要）
    - IO レベルのルーティング（target_role ≠ mind は直接セッションに転送）

    設計:
    - 通常メッセージ: EventBus.publish(InputReady) のみ（send-only）
    - system メッセージ: 同期レスポンスが必要なためコールバック維持
    - command メッセージ: 同期レスポンスが必要なためコールバック維持
    """

    def __init__(
        self,
        session_manager: SessionManager,
        event_bus: Any,
        command_handler: Callable[..., str] | None = None,
    ) -> None:
        self._session_mgr = session_manager
        self._event_bus = event_bus
        self._cmd_handler = command_handler
        self._system_handler: Callable[[SystemMessage, str], SystemMessage | None] | None = None

    def set_command_handler(self, handler: Callable[..., str]) -> None:
        self._cmd_handler = handler

    def set_system_handler(self, handler: Callable[[SystemMessage, str], SystemMessage | None]) -> None:
        """system メッセージのハンドラを設定する。

        handler は gRPC の SystemMessage と session_id を受け取り、
        レスポンスの SystemMessage または None を返す。
        同期レスポンスが必要なため、コールバック pattern を維持する。
        """
        self._system_handler = handler

    def on_grpc_system(self, sys_msg: SystemMessage, session_id: str, session_role: str) -> None:
        if not self._system_handler:
            return
        result = self._system_handler(sys_msg, session_id)
        if result is not None:
            self._session_mgr.route_system_message(result, session_id)

    def on_grpc_message(self, msg: Message) -> None:
        """通常メッセージを EventBus に publish する（send-only）。

        IO ルーティング: target_role ≠ mind は直接セッションに転送。
        mind 対象のメッセージは InputReady イベントとして publish し、
        memory 層が subscribe して処理する。
        """
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
            InputReady(
                timestamp=None,
                source="io",
                session_id=msg.session_id,
                content=msg.content,
                user_id=msg.user_id,
                context={
                    "source_role": msg.source_role,
                    "target_role": msg.target_role,
                    "msg_type": msg.msg_type,
                },
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

        result = self._cmd_handler(name, args, msg.session_id) if self._cmd_handler else f"No command handler: /{name}"

        logger.debug("IOGateway: command result session={} result={:.100}", msg.session_id, result)
        self._session_mgr.route_command_output(
            msg.session_id,
            CommandOutput(content=result, session_id=msg.session_id, correlation_id=msg.id),
        )
