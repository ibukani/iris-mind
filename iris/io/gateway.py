"""IO層のアダプタ。gRPC と内部レイヤーの橋渡しを行う。

責務:
- gRPC メッセージを内部表現に変換し、EventBus に publish する
- ControlMessage / CommandInput は DispatcherRegistry 経由でルーティング

設計:
- 通常メッセージ: EventBus.publish(InputReady) のみ（send-only）
- control / command メッセージ: DispatcherRegistry で優先度順にルーティング
- 抑制制御 (msg_type="inhibition") は専用ハンドラで InhibitionRequestEvent に変換
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from loguru import logger

from iris.io.dispatcher import DispatcherRegistry
from iris.io.events import ControlMessageEvent, InhibitionRequestEvent, InputReady
from iris.io.models import CommandInput, CommandOutput, ControlMessage, Direction, Message, TransportIdentity

if TYPE_CHECKING:
    from iris.account.manager import AccountManager
    from iris.io.session.manager import SessionManager
    from iris.room.store import RoomStore


class _IOGateway:
    def __init__(
        self,
        session_manager: SessionManager,
        event_bus: Any,
        dispatcher: DispatcherRegistry,
        room_store: RoomStore | None = None,
        account_manager: AccountManager | None = None,
    ) -> None:
        self._session_mgr = session_manager
        self._event_bus = event_bus
        self._dispatcher = dispatcher
        self._room_store = room_store
        self._account_manager = account_manager

    def _build_control_message(self, response: Any) -> ControlMessage:
        identity = getattr(response, "identity", None)
        return ControlMessage(
            action=getattr(response, "action", ""),
            account_id=getattr(response, "account_id", ""),
            room_id=getattr(response, "room_id", ""),
            display_name=getattr(response, "display_name", ""),
            text=getattr(response, "text", ""),
            identity=TransportIdentity(**identity) if isinstance(identity, dict) else identity,
            profile=getattr(response, "profile", None) or {},
            metadata=getattr(response, "metadata", None) or {},
        )

    def _send_error(self, orig: Message, text: str) -> None:
        session_info = self._session_mgr.get_session_info(orig.session_id)
        target_role = session_info.role if session_info else "*"
        self._session_mgr.router.route_message(
            Message(
                msg_type="response",
                content=text,
                session_id=orig.session_id,
                source_role="mind",
                target_role=target_role,
                direction=Direction.RESPONSE,
                account_id=orig.account_id,
                metadata={"error": "true"},
            ),
        )

    def _publish_inhibition_request(self, msg: Message) -> None:
        """msg_type="inhibition" の Message を InhibitionRequestEvent に変換して publish する。

        content フォーマット: "reason:action[:duration]"
          - "voice_recording:true"     → suppress
          - "voice_recording:false"    → unsuppress
          - "speaking:true:30.0"       → suppress（30秒間）
          - "hyperdirect:true"         → 緊急停止
        """
        parts = msg.content.split(":")
        if len(parts) < 2:
            logger.warning(
                "IOGateway: invalid inhibition content '{}', expected 'reason:action[:duration]'",
                msg.content,
            )
            return

        reason = parts[0]
        action = parts[1]
        duration = 0.0
        if len(parts) >= 3:
            try:
                duration = float(parts[2])
            except ValueError:
                logger.warning("IOGateway: invalid inhibition duration '{}', ignoring", parts[2])
                return

        self._event_bus.publish(
            InhibitionRequestEvent(
                timestamp=None,
                source="io",
                action=action,
                reason=reason,
                duration=duration,
                room_id=msg.room_id,
                session_id=msg.session_id,
            )
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

        ctx: dict[str, Any] = {
            "msg": evt,
            "type": "control",
            "session_id": session_id,
            "response": None,
        }
        result = self._dispatcher.dispatch_control(ctx)

        self._event_bus.publish(evt)

        response = result.get("response")
        if response is None:
            return

        self._session_mgr.router.route_control_message(self._build_control_message(response), session_id)

    def on_grpc_message(self, msg: Message) -> None:
        """通常メッセージを EventBus に publish する（send-only）。"""
        if msg.direction != Direction.REQUEST:
            self._send_error(msg, f"unexpected direction from client: {msg.direction}. use 'request'")
            return

        if msg.target_role != "mind":
            self._session_mgr.router.route_message(msg)
            return

        if msg.speaker is None:
            self._send_error(msg, "speaker is required for inbound messages")
            return

        if msg.msg_type == "inhibition":
            self._publish_inhibition_request(msg)
            return

        if msg.msg_type == "chat" and not msg.content:
            self._send_error(msg, "content is required for chat messages")
            return

        if not msg.room_id:
            self._send_error(msg, "room_id is required")
            return

        account_id = msg.account_id
        if not account_id and msg.speaker and self._account_manager is not None:
            from iris.account.models import Provider

            try:
                provider = Provider(msg.speaker.provider)
                speaker_meta = msg.speaker.metadata
                metadata_obj: dict[str, object] | None = dict(speaker_meta) if isinstance(speaker_meta, dict) else None
                account = self._account_manager.resolve_or_create_identity(
                    provider,
                    msg.speaker.subject,
                    provider_name=msg.speaker.provider_name,
                    metadata=metadata_obj,
                )
                account_id = str(account.account_id)
            except Exception as e:
                logger.error("IOGateway: failed to resolve account: {}", e)

        if self._room_store is not None and not self._room_store.find_room_by_id(msg.room_id):
            self._send_error(msg, f"room not found: {msg.room_id}")
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
                account_id=account_id,
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
            err = "Commands start with /"
            logger.debug("IOGateway: command missing slash session={}", msg.session_id)
            self._session_mgr.router.route_command_output(
                msg.session_id,
                CommandOutput(content=err, session_id=msg.session_id, correlation_id=msg.id),
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
        result: dict[str, Any] = self._dispatcher.dispatch_command(ctx)

        response = result.get("response") or f"No command handler: /{name}"

        logger.debug("IOGateway: command result session={} result={:.100}", msg.session_id, response)
        self._session_mgr.router.route_command_output(
            msg.session_id,
            CommandOutput(content=response, session_id=msg.session_id, correlation_id=msg.id),
        )


__all__ = ["_IOGateway"]
