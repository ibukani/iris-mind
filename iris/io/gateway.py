from __future__ import annotations

from typing import TYPE_CHECKING, Any

from loguru import logger

from iris.event.event_types import ControlMessageEvent, InputReady
from iris.io.models import CommandInput, CommandOutput, ControlMessage, Direction, Identity, Message

if TYPE_CHECKING:
    from iris.io.session.manager import SessionManager
    from iris.kernel.plugin.hooks import HookRegistry


class _IOGateway:
    """IO層のアダプタ。gRPC と内部レイヤーの橋渡しを行う。

    責務:
    - gRPC メッセージを内部表現に変換し、EventBus に publish する
    - command / control メッセージは io.dispatch Hook 経由でルーティング

    設計:
    - 通常メッセージ: EventBus.publish(InputReady) のみ（send-only）
    - command / control メッセージ: io.dispatch Hook で同期ルーティング
    """

    def __init__(
        self,
        session_manager: SessionManager,
        event_bus: Any,
        hook_registry: HookRegistry,
    ) -> None:
        self._session_mgr = session_manager
        self._event_bus = event_bus
        self._hook_registry = hook_registry

    def _build_control_message(self, response: Any) -> ControlMessage:
        identity = getattr(response, "identity", None)
        return ControlMessage(
            action=getattr(response, "action", ""),
            account_id=getattr(response, "account_id", ""),
            room_id=getattr(response, "room_id", ""),
            display_name=getattr(response, "display_name", ""),
            text=getattr(response, "text", ""),
            identity=Identity(**identity) if isinstance(identity, dict) else identity,
            profile=getattr(response, "profile", None) or {},
            metadata=getattr(response, "metadata", None) or {},
        )

    def on_grpc_control(self, control_msg: ControlMessage, session_id: str, session_role: str) -> None:
        evt = ControlMessageEvent(
            timestamp=None,
            source="io",
            action=control_msg.action,
            account_id=control_msg.account_id,
            room_id=control_msg.room_id,
            display_name=control_msg.display_name,
            text=control_msg.text,
            session_id=session_id,
            identity=control_msg.identity.model_dump() if control_msg.identity else None,
            profile=control_msg.profile,
            metadata=control_msg.metadata,
        )

        ctx: dict[str, Any] = {"msg": evt, "type": "control", "session_id": session_id, "response": None}
        result = self._hook_registry.execute_sync("io.dispatch", ctx)

        self._event_bus.publish(evt)

        response = result.get("response")
        if response is None:
            return

        self._session_mgr.router.route_control_message(self._build_control_message(response), session_id)

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
            self._session_mgr.router.route_message(msg)
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
                account_id=msg.account_id,
                room_id=msg.room_id,
                context={
                    "source_role": msg.source_role,
                    "target_role": msg.target_role,
                    "msg_type": msg.msg_type,
                    "speaker": msg.speaker.model_dump() if msg.speaker else None,
                    "room_id": msg.room_id,
                },
            ),
        )

    def on_grpc_command(self, msg: CommandInput) -> None:
        content = msg.content
        if not content.startswith("/"):
            result = "Commands start with /"
            logger.debug("IOGateway: command missing slash session={}", msg.session_id)
            self._session_mgr.router.route_command_output(
                msg.session_id,
                CommandOutput(content=result, session_id=msg.session_id, correlation_id=msg.id),
            )
            return

        parts = content[1:].strip().split(maxsplit=1)
        name = parts[0].lower() if parts else ""
        args = parts[1] if len(parts) > 1 else ""

        logger.debug("IOGateway: command session={} cmd=/{} args={:.100}", msg.session_id, name, args)

        ctx: dict[str, Any] = {
            "msg": msg,
            "type": "command",
            "name": name,
            "args": args,
            "session_id": msg.session_id,
            "response": None,
        }
        result = self._hook_registry.execute_sync("io.dispatch", ctx)

        response = result.get("response") or f"No command handler: /{name}"

        logger.debug("IOGateway: command result session={} result={:.100}", msg.session_id, response)
        self._session_mgr.router.route_command_output(
            msg.session_id,
            CommandOutput(content=response, session_id=msg.session_id, correlation_id=msg.id),
        )
