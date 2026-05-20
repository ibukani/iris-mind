from __future__ import annotations

import asyncio
from collections.abc import Callable
import contextlib
import json
import logging
import threading
from typing import Any

import grpc

from iris.io.models import AuthMessage, CommandInput, Direction, Message, Permission
from iris.io.session.manager import SessionManager
from iris.io.transport import grpc_service_pb2, grpc_service_pb2_grpc

logger = logging.getLogger(__name__)


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
    ) -> None:
        self._session_manager = session_manager
        self._on_message = on_message or self._noop
        self._on_command = on_command
        self._server: grpc.aio.Server | None = None

    @staticmethod
    def _noop(_msg: Message) -> None:
        return

    def set_on_message(self, on_message: Callable[[Message], None]) -> None:
        self._on_message = on_message

    def set_on_command(self, on_command: Callable[[CommandInput], None]) -> None:
        self._on_command = on_command

    async def start(self, host: str, port: int) -> None:
        self._server = grpc.aio.server()
        grpc_service_pb2_grpc.add_IrisServiceServicer_to_server(self, self._server)
        self._server.add_insecure_port(f"{host}:{port}")
        await self._server.start()
        logger.info("GrpcServer started on %s:%d", host, port)

    async def stop(self) -> None:
        if self._server:
            # 終了処理を非同期で行う
            await self._server.stop(grace=1.0)
            self._server = None
            logger.info("GrpcServer stopped")

    async def BidirectionalStream(self, request_iterator: Any, context: Any) -> Any:
        # 1. 認証 (Metadataの読み取り)
        metadata = dict(context.invocation_metadata())

        perms_str = metadata.get("permissions", "")
        permissions = []
        if perms_str:
            for p in perms_str.split(","):
                p = p.strip()
                if p:
                    try:
                        permissions.append(Permission(p))
                    except ValueError:
                        logger.warning("GrpcServer: invalid permission metadata %s", p)

        auth_msg = AuthMessage(
            msg_type="auth",
            access_token=metadata.get("access_token"),
            role=metadata.get("role", "external"),
            permissions=permissions,
            identity=metadata.get("identity", ""),
            description=metadata.get("description", ""),
        )

        loop = asyncio.get_running_loop()
        grpc_conn = GrpcConnection(loop)

        auth_res = self._session_manager.authenticate(grpc_conn, auth_msg)
        if auth_res.msg_type == "auth_failure":
            logger.warning("GrpcServer: authentication failed: %s", auth_res.error_message)
            await context.abort(grpc.StatusCode.UNAUTHENTICATED, auth_res.error_message or "Auth failed")
            return

        session_id = auth_res.session_id
        assert session_id is not None
        session_role = auth_msg.role or "external"
        logger.info("GrpcServer: session %s authenticated (role=%s)", session_id, session_role)

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
        receive_task = asyncio.create_task(self._receive_loop(request_iterator, session_id, session_role))

        try:
            # 3. 送信ループ (Server -> Client)
            while True:
                raw = await grpc_conn.queue.get()
                data = json.loads(raw.decode("utf-8"))

                msg_type = data.get("msg_type", "")
                frame = grpc_service_pb2.BidirectionalStreamResponse()  # type: ignore[attr-defined]

                if msg_type == "command":
                    cmd_out = grpc_service_pb2.CommandOutput(  # type: ignore[attr-defined]
                        id=data.get("id", ""),
                        correlation_id=data.get("correlation_id", ""),
                        session_id=data.get("session_id", ""),
                        msg_type=data.get("msg_type", ""),
                        content=data.get("content", ""),
                        state=data.get("state") or "",
                    )
                    frame.command.CopyFrom(cmd_out)
                else:
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
                    for k, v in meta.items():
                        msg.metadata[k] = str(v)
                    frame.message.CopyFrom(msg)

                yield frame

        except asyncio.CancelledError:
            pass
        finally:
            receive_task.cancel()
            await asyncio.gather(receive_task, return_exceptions=True)
            self._session_manager.remove_session(session_id)
            logger.info("GrpcServer: session %s disconnected", session_id)

    async def _receive_loop(self, request_iterator: Any, session_id: str, session_role: str) -> None:
        try:
            async for client_frame in request_iterator:
                self._session_manager.update_activity(session_id)
                frame_type = client_frame.WhichOneof("frame")

                if frame_type == "message":
                    await self._dispatch_message(client_frame.message, session_id, session_role)
                elif frame_type == "command":
                    await self._handle_command(client_frame.command, session_id, session_role)
                else:
                    logger.warning("GrpcServer: unknown frame type received")

        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("GrpcServer error in receive loop for session %s", session_id)

    async def _dispatch_message(self, msg_proto: Any, session_id: str, session_role: str) -> None:
        metadata = {}
        for k, v in msg_proto.metadata.items():
            if v.lower() == "true":
                metadata[k] = True
            elif v.lower() == "false":
                metadata[k] = False
            else:
                metadata[k] = v

        try:
            msg = Message(
                id=msg_proto.id,
                correlation_id=msg_proto.correlation_id or None,
                session_id=session_id,
                source_role=session_role,
                target_role=msg_proto.target_role or "*",
                direction=Direction(msg_proto.direction),
                msg_type=msg_proto.msg_type,
                content=msg_proto.content,
                content_type=msg_proto.content_type or "text/plain",
                state=msg_proto.state or None,
                metadata=metadata,
            )
        except Exception:
            logger.warning("GrpcServer: invalid message parse failed")
            return

        if not self._session_manager.is_session_active(session_id):
            logger.warning("GrpcServer: message from inactive session: %s", session_id)
            return

        if not self._session_manager.check_send_permission(session_id, msg.msg_type):
            logger.warning("GrpcServer: session=%s lacks permission for msg_type=%s", session_id, msg.msg_type)
            err = Message(
                msg_type="error",
                content=f"Permission denied: cannot send {msg.msg_type}",
                source_role="mind",
                target_role=session_role,
                session_id=session_id,
                direction=Direction.RESPONSE,
            )
            self._session_manager.route_message(err)
            return

        await asyncio.to_thread(self._on_message, msg)

        if msg.metadata.get("ack_required", False):
            ack = Message(
                msg_type="ack",
                content=f"ack:{msg.id}",
                correlation_id=msg.id,
                source_role="mind",
                target_role=session_role,
                session_id=session_id,
                direction=Direction.RESPONSE,
            )
            self._session_manager.route_message(ack)

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

        if not self._session_manager.is_session_active(session_id):
            logger.warning("GrpcServer: command from inactive session: %s", session_id)
            return

        if not self._session_manager.check_send_permission(session_id, "command"):
            logger.warning("GrpcServer: session=%s lacks permission to send command", session_id)
            return

        if self._on_command:
            await asyncio.to_thread(self._on_command, cmd)


class GrpcListener:
    """GrpcListener。同期スレッド上でgRPCサーバーを管理する。"""

    def __init__(
        self,
        session_manager: SessionManager,
        on_message: Callable[[Message], None] | None = None,
        on_command: Callable[[CommandInput], None] | None = None,
    ) -> None:
        self._session_manager = session_manager
        self._on_message = on_message
        self._on_command = on_command
        self._server_impl: GrpcServer | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None

    def set_on_message(self, on_message: Callable[[Message], None]) -> None:
        self._on_message = on_message
        if self._server_impl:
            self._server_impl.set_on_message(on_message)

    def set_on_command(self, on_command: Callable[[CommandInput], None]) -> None:
        self._on_command = on_command
        if self._server_impl:
            self._server_impl.set_on_command(on_command)

    def start(self, host: str, port: int) -> None:
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_server, args=(host, port), daemon=True, name="grpc-listener")
        self._thread.start()

    def stop(self) -> None:
        loop = self._loop
        server = self._server_impl
        if loop is not None and server is not None:

            async def _cleanup() -> None:
                try:
                    await server.stop()
                except Exception:
                    logger.exception("Error stopping gRPC server")
                finally:
                    loop.stop()

            if loop.is_running():
                loop.call_soon_threadsafe(lambda: asyncio.create_task(_cleanup()))
            else:
                loop.stop()

        if self._thread:
            self._thread.join(timeout=3)
            self._thread = None

        if loop is not None:
            with contextlib.suppress(Exception):
                loop.close()
            self._loop = None
        logger.info("GrpcListener stopped")

    def _run_server(self, host: str, port: int) -> None:
        assert self._loop is not None
        asyncio.set_event_loop(self._loop)
        self._server_impl = GrpcServer(
            self._session_manager,
            on_message=self._on_message,
            on_command=self._on_command,
        )
        try:
            self._loop.run_until_complete(self._server_impl.start(host, port))
            self._loop.run_forever()
        except Exception:
            logger.exception("GrpcListener server thread encountered an error")
