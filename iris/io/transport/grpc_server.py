from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Callable
import contextlib
from typing import Any

import grpc
from loguru import logger
import orjson

from iris.io.models import AuthMessage, CommandInput, ControlMessage, Direction, Identity, Message, Permission
from iris.io.session.manager import SessionManager
from iris.io.transport import grpc_service_pb2, grpc_service_pb2_grpc


class GrpcConnection:
    """SessionManagerのConnection互換インターフェース。
    同期スレッドのSessionManagerから非同期のgRPC送信タスクへデータを送るためのキューラッパー。
    """

    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        self.queue: asyncio.Queue[bytes] = asyncio.Queue()
        self.loop = loop

    def send_bytes(self, raw: bytes) -> None:
        """同期コンテキストから非同期キューへスレッドセーフに投入する"""
        self.loop.call_soon_threadsafe(self.queue.put_nowait, raw)

    def close(self) -> None:
        """互換用のダミーメソッド"""


class GrpcServer(grpc_service_pb2_grpc.IrisServiceServicer):
    """gRPC双方向ストリーミングサーバーの実装。"""

    def __init__(
        self,
        session_manager: SessionManager,
        on_message: Callable[[Message], None] | None = None,
        on_command: Callable[[CommandInput], None] | None = None,
        on_control_message: Callable[[ControlMessage, str, str], None] | None = None,
    ) -> None:
        self._session_manager = session_manager
        self._on_message = on_message or self._noop
        self._on_command = on_command
        self._on_control_message = on_control_message
        self._server: grpc.aio.Server | None = None

    @staticmethod
    def _noop(_msg: Message) -> None:
        return

    def set_on_message(self, on_message: Callable[[Message], None]) -> None:
        self._on_message = on_message

    def set_on_command(self, on_command: Callable[[CommandInput], None]) -> None:
        self._on_command = on_command

    def set_on_control_message(self, on_control_message: Callable[[ControlMessage, str, str], None]) -> None:
        self._on_control_message = on_control_message

    async def start(self, host: str, port: int) -> None:
        self._server = grpc.aio.server()
        grpc_service_pb2_grpc.add_IrisServiceServicer_to_server(self, self._server)
        self._server.add_insecure_port(f"{host}:{port}")
        await self._server.start()
        logger.info("GrpcServer started on {}:{}", host, port)

    async def stop(self) -> None:
        if self._server:
            # 終了処理を非同期で行う
            await self._server.stop(grace=1.0)
            self._server = None
            logger.info("GrpcServer stopped")

    def _parse_permissions(self, perms_str: str) -> list[Permission]:
        """カンマ区切りの権限文字列をパースしてPermissionリストを返す。"""
        permissions = []
        if perms_str:
            for p in perms_str.split(","):
                p = p.strip()
                if p:
                    try:
                        permissions.append(Permission(p))
                    except ValueError:
                        logger.warning("GrpcServer: invalid permission metadata {}", p)
        return permissions

    async def _authenticate(self, metadata: dict[str, str], grpc_conn: GrpcConnection, context: Any) -> tuple[str, str]:
        """セッションの認証を行い、成功した場合は (session_id, session_role) を返す。"""
        perms_str = metadata.get("permissions", "")
        permissions = self._parse_permissions(perms_str)

        auth_msg = AuthMessage(
            msg_type="auth",
            access_token=metadata.get("access_token"),
            role=metadata.get("role", "external"),
            permissions=permissions,
            identity=metadata.get("identity", ""),
            description=metadata.get("description", ""),
            user_id=metadata.get("user_id", ""),
        )

        auth_res = self._session_manager.authenticate(grpc_conn, auth_msg)
        if auth_res.msg_type == "auth_failure":
            logger.warning("GrpcServer: authentication failed: {}", auth_res.error_message)
            await context.abort(grpc.StatusCode.UNAUTHENTICATED, auth_res.error_message or "Auth failed")
            raise ConnectionError("Authentication failed")

        session_id = auth_res.session_id
        assert session_id is not None
        session_role = auth_msg.role or "external"
        logger.info("GrpcServer: session {} authenticated (role={})", session_id, session_role)
        return session_id, session_role

    async def BidirectionalStream(self, request_iterator: Any, context: Any) -> Any:
        metadata = dict(context.invocation_metadata())
        loop = asyncio.get_running_loop()
        grpc_conn = GrpcConnection(loop)

        try:
            session_id, session_role = await self._authenticate(metadata, grpc_conn, context)
        except ConnectionError:
            return

        # 2. 認証成功をクライアントに通知（デッドロック防止）
        ack = grpc_service_pb2.Message(  # type: ignore[attr-defined]
            id="",
            msg_type="auth_success",
            session_id=session_id,
            direction="response",
            content="authenticated",
        )
        yield grpc_service_pb2.BidirectionalStreamResponse(message=ack)  # type: ignore[attr-defined]

        # 3. 受信ループ起動 (Client -> Server)
        receive_task = asyncio.create_task(self._receive_loop(request_iterator, session_id, session_role, grpc_conn))

        try:
            # 3. 送信ループ (Server -> Client)
            async for frame in self._stream_send_loop(grpc_conn):
                yield frame

        except asyncio.CancelledError:
            pass
        except GeneratorExit:
            return
        finally:
            receive_task.cancel()
            with contextlib.suppress(Exception):
                await asyncio.gather(receive_task, return_exceptions=True)
            self._session_manager.remove_session(session_id)
            logger.info("GrpcServer: session {} disconnected", session_id)

    async def _stream_send_loop(self, grpc_conn: GrpcConnection) -> AsyncGenerator[Any]:
        while True:
            raw = await grpc_conn.queue.get()
            data = orjson.loads(raw)
            msg_type = data.get("msg_type", "")
            action = data.get("action")
            frame = grpc_service_pb2.BidirectionalStreamResponse()  # type: ignore[attr-defined]

            if msg_type == "command":
                cmd_out = self._build_command_frame(data)
                frame.command.CopyFrom(cmd_out)
            elif action:
                control_out = grpc_service_pb2.ControlMessage(  # type: ignore[attr-defined]
                    action=action,
                    account_id=data.get("account_id", ""),
                    room_id=data.get("room_id", ""),
                    nickname=data.get("nickname", ""),
                )
                text = data.get("text")
                if text:
                    control_out.text = text
                identity = data.get("identity")
                if isinstance(identity, dict):
                    control_out.identity.CopyFrom(self._build_identity_frame(identity))
                profile = data.get("profile", {})
                if isinstance(profile, dict):
                    for k, v in profile.items():
                        control_out.profile[str(k)] = str(v)
                metadata = data.get("metadata", {})
                if isinstance(metadata, dict):
                    for k, v in metadata.items():
                        control_out.metadata[str(k)] = str(v)
                frame.control.CopyFrom(control_out)
            else:
                msg = self._build_message_frame(data)
                frame.message.CopyFrom(msg)

            yield frame

    @staticmethod
    def _build_command_frame(data: dict[str, Any]) -> Any:
        return grpc_service_pb2.CommandOutput(  # type: ignore[attr-defined]
            id=data.get("id", ""),
            correlation_id=data.get("correlation_id", ""),
            session_id=data.get("session_id", ""),
            msg_type=data.get("msg_type", ""),
            content=data.get("content", ""),
            state=data.get("state") or "",
        )

    @staticmethod
    def _build_message_frame(data: dict[str, Any]) -> Any:
        msg = grpc_service_pb2.Message(  # type: ignore[attr-defined]
            id=data.get("id", ""),
            correlation_id=data.get("correlation_id", ""),
            session_id=data.get("session_id", ""),
            source_role=data.get("source_role", ""),
            target_role=data.get("target_role", ""),
            direction=data.get("direction", ""),
            msg_type=data.get("msg_type", ""),
            content=data.get("content", ""),
            content_type=data.get("content_type", ""),
            state=data.get("state") or "",
        )
        meta = data.get("metadata", {})
        uid = data.get("user_id", "")
        if uid:
            meta["user_id"] = uid
        room_id = data.get("room_id", "")
        if room_id:
            msg.room_id = room_id
        for k, v in meta.items():
            msg.metadata[k] = str(v)
        speaker = data.get("speaker")
        if isinstance(speaker, dict):
            msg.speaker.CopyFrom(GrpcServer._build_identity_frame(speaker))
        return msg

    @staticmethod
    def _build_identity_frame(data: dict[str, Any]) -> Any:
        identity = grpc_service_pb2.Identity(  # type: ignore[attr-defined]
            provider=str(data.get("provider", "")),
            subject=str(data.get("subject", "")),
            display_name=str(data.get("display_name", "")),
        )
        metadata = data.get("metadata", {})
        if isinstance(metadata, dict):
            for k, v in metadata.items():
                identity.metadata[str(k)] = str(v)
        return identity

    async def _receive_loop(
        self,
        request_iterator: Any,
        session_id: str,
        session_role: str,
        grpc_conn: GrpcConnection,
    ) -> None:
        try:
            async for client_frame in request_iterator:
                self._session_manager.update_activity(session_id)
                frame_type = client_frame.WhichOneof("frame")

                if frame_type == "message":
                    await self._dispatch_message(client_frame.message, session_id, session_role)
                elif frame_type == "command":
                    await self._handle_command(client_frame.command, session_id, session_role)
                elif frame_type == "control":
                    await self._dispatch_control(client_frame.control, session_id, session_role)
                else:
                    logger.warning("GrpcServer: unknown frame type received")

        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("GrpcServer error in receive loop for session {}", session_id)

    def _parse_message_metadata(self, metadata_proto: Any) -> dict[str, Any]:
        """gRPCのメッセージメタデータをPythonの辞書に変換・パースする。"""
        metadata = {}
        for k, v in metadata_proto.items():
            if v.lower() == "true":
                metadata[k] = True
            elif v.lower() == "false":
                metadata[k] = False
            else:
                metadata[k] = v
        return metadata

    def _validate_session(self, session_id: str, msg_type: str, log_label: str = "message") -> bool:
        if not self._session_manager.is_session_active(session_id):
            logger.warning("GrpcServer: {} from inactive session: {}", log_label, session_id)
            return False
        if not self._session_manager.check_send_permission(session_id, msg_type):
            logger.warning("GrpcServer: session={} lacks permission for {}", session_id, msg_type)
            return False
        return True

    def _send_ack(self, correlation_id: str, session_role: str, session_id: str) -> None:
        ack = Message(
            msg_type="ack",
            content=f"ack:{correlation_id}",
            correlation_id=correlation_id,
            source_role="mind",
            target_role=session_role,
            session_id=session_id,
            direction=Direction.RESPONSE,
        )
        self._session_manager.route_message(ack)

    async def _dispatch_message(self, msg_proto: Any, session_id: str, session_role: str) -> None:
        metadata = self._parse_message_metadata(msg_proto.metadata)

        try:
            msg = Message(
                id=msg_proto.id,
                correlation_id=msg_proto.correlation_id or None,
                session_id=session_id,
                source_role=session_role,
                target_role=msg_proto.target_role or "*",
                user_id=metadata.get("user_id", ""),
                direction=Direction(msg_proto.direction),
                msg_type=msg_proto.msg_type,
                content=msg_proto.content,
                content_type=msg_proto.content_type or "text/plain",
                state=msg_proto.state or None,
                metadata=metadata,
                speaker=self._parse_identity(msg_proto.speaker),
                room_id=msg_proto.room_id,
            )
        except Exception:
            logger.warning("GrpcServer: invalid message parse failed")
            return

        if not self._validate_session(session_id, msg.msg_type):
            return

        await asyncio.to_thread(self._on_message, msg)

        if msg.metadata.get("ack_required", False):
            self._send_ack(msg.id, session_role, session_id)

    async def _handle_command(self, cmd_proto: Any, session_id: str, session_role: str) -> None:
        try:
            cmd = CommandInput(
                msg_type="command",
                id=cmd_proto.id,
                session_id=session_id,
                source_role=session_role,
                content=cmd_proto.content,
            )
        except Exception:
            logger.warning("GrpcServer: invalid command parse failed")
            return

        if not self._validate_session(session_id, "command", log_label="command"):
            return

        if self._on_command:
            await asyncio.to_thread(self._on_command, cmd)

    async def _dispatch_control(self, control_proto: Any, session_id: str, session_role: str) -> None:
        if self._on_control_message is None:
            logger.warning("GrpcServer: no control message handler for session {}", session_id)
            return
        try:
            control_msg = ControlMessage(
                action=control_proto.action,
                account_id=control_proto.account_id,
                room_id=control_proto.room_id,
                nickname=control_proto.nickname,
                text=control_proto.text,
                identity=self._parse_identity(control_proto.identity),
                profile=dict(control_proto.profile),
                metadata=dict(control_proto.metadata),
            )
        except Exception:
            logger.warning("GrpcServer: invalid control message parse failed")
            return

        await asyncio.to_thread(self._on_control_message, control_msg, session_id, session_role)

    @staticmethod
    def _parse_identity(identity_proto: Any) -> Identity | None:
        if not identity_proto.provider and not identity_proto.subject:
            return None
        return Identity(
            provider=identity_proto.provider,
            subject=identity_proto.subject,
            display_name=identity_proto.display_name,
            metadata=dict(identity_proto.metadata),
        )
