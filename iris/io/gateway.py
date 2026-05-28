from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from loguru import logger

from iris.io.models import CommandInput, CommandOutput, Direction, Message, SystemMessage

if TYPE_CHECKING:
    from iris.io.session.manager import SessionManager


class _IOGateway:
    """IO層のアダプタ。gRPC と内部レイヤーの橋渡しを行う。

    責務:
    - gRPC メッセージを内部表現に変換し、適切なハンドラに渡す
    - ハンドラからのレスポンスを gRPC 経由でクライアントに返す
    - IO レベルのルーティング（target_role ≠ mind は直接セッションに転送）

    注意:
    - EventBus は直接利用しない。EventBus 経由の通信は memory 層（handler）が担当する。
    - Gateway は IO アダプタとしての責務のみを持ち、イベントの publish/subscribe は行わない。
    - 全メッセージパス（system, message, command）で handler コールバック pattern を統一する。
    """

    def __init__(
        self,
        session_manager: SessionManager,
        command_handler: Callable[..., str] | None = None,
    ) -> None:
        self._session_mgr = session_manager
        self._cmd_handler = command_handler
        self._system_handler: Callable[[SystemMessage, str], SystemMessage | None] | None = None
        self._message_handler: Callable[[Message], None] | None = None

    def set_command_handler(self, handler: Callable[..., str]) -> None:
        self._cmd_handler = handler

    def set_system_handler(self, handler: Callable[[SystemMessage, str], SystemMessage | None]) -> None:
        """system メッセージのハンドラを設定する。

        handler は gRPC の SystemMessage と session_id を受け取り、
        レスポンスの SystemMessage または None を返す。
        EventBus の publish/subscribe は handler 側で行う。
        """
        self._system_handler = handler

    def set_message_handler(self, handler: Callable[[Message], None]) -> None:
        """通常メッセージのハンドラを設定する。

        handler は Message を受け取り、EventBus への publish を含む処理を行う。
        Gateway は IO アダプタとしての責務のみを持ち、EventBus を直接操作しない。
        """
        self._message_handler = handler

    def on_grpc_system(self, sys_msg: SystemMessage, session_id: str, session_role: str) -> None:
        if not self._system_handler:
            return
        result = self._system_handler(sys_msg, session_id)
        if result is not None:
            self._session_mgr.route_system_message(result, session_id)

    def on_grpc_message(self, msg: Message) -> None:
        """通常メッセージをハンドラに渡す。

        IO ルーティング: target_role ≠ mind は直接セッションに転送。
        mind 対象のメッセージは handler コールバックに渡す。
        handler 内部で EventBus に publish し、memory 層が処理する。
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

        if self._message_handler:
            self._message_handler(msg)

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
