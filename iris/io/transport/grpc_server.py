from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Callable
import contextlib
from typing import Any

import grpc
from loguru import logger
import orjson

from iris.io.models import AuthMessage, CommandInput, ControlMessage, Direction, Message, Permission
from iris.io.session.manager import SessionManager
from iris.io.transport import grpc_service_pb2, grpc_service_pb2_grpc
from iris.io.transport.formatter import (
    build_command_frame,
    build_identity_frame,
    build_message_frame,
    parse_identity,
    parse_message_metadata,
)


def _noop(_msg: Message) -> None:
    return


def _set_proto_from_dict(proto_repeated: Any, value: Any, builder: Any) -> None:
    if isinstance(value, dict):
        result = builder(value)
        if isinstance(result, dict):
            for k, v in result.items():
                proto_repeated[str(k)] = str(v)
        else:
            proto_repeated.CopyFrom(result)


class GrpcConnection:
    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        self.queue: asyncio.Queue[bytes] = asyncio.Queue()
        self.loop = loop

    def send_bytes(self, raw: bytes) -> None:
        self.loop.call_soon_threadsafe(self.queue.put_nowait, raw)

    def close(self) -> None:
        pass


class GrpcServer(grpc_service_pb2_grpc.IrisServiceServicer):
    def __init__(
        self,
        session_manager: SessionManager,
        on_message: Callable[[Message], None] | None = None,
        on_command: Callable[[CommandInput], None] | None = None,
        on_control_message: Callable[[ControlMessage, str, str], None] | None = None,
    ) -> None:
        self._session_manager = session_manager
        self._on_message = on_message or _noop
        self._on_command = on_command
        self._on_control_message = on_control_message
        self._server: grpc.aio.Server | None = None

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
        if self._server is None:
            return
        await self._server.stop(grace=1.0)
        self._server = None
        logger.info("GrpcServer stopped")

    def _parse_permissions(self, perms_str: str) -> list[Permission]:
        if not perms_str:
            return []
        permissions = []
        for p in perms_str.split(","):
            p = p.strip()
            if not p:
                continue
            try:
                permissions.append(Permission(p))
            except ValueError:
                logger.warning("GrpcServer: invalid permission metadata {}", p)
        return permissions

    async def _authenticate(
        self,
        metadata: dict[str, str],
        grpc_conn: GrpcConnection,
        context: Any,
    ) -> tuple[str, str]:
        perms_str = metadata.get("permissions", "")
        permissions = self._parse_permissions(perms_str)

        auth_msg = AuthMessage(
            msg_type="auth",
            access_token=metadata.get("access_token"),
            role=metadata.get("role", "external"),
            permissions=permissions,
            session_tag=metadata.get("session_tag", ""),
            description=metadata.get("description", ""),
        )

        auth_res = self._session_manager.authenticate(grpc_conn, auth_msg)
        if auth_res.msg_type != "auth_failure":
            session_id = auth_res.session_id
            assert session_id is not None
            session_role = auth_msg.role or "external"
            logger.info("GrpcServer: session {} authenticated (role={})", session_id, session_role)
            return session_id, session_role

        logger.warning("GrpcServer: authentication failed: {}", auth_res.error_message)
        await context.abort(grpc.StatusCode.UNAUTHENTICATED, auth_res.error_message or "Auth failed")
        raise ConnectionError("Authentication failed")

    async def BidirectionalStream(self, request_iterator: Any, context: Any) -> Any:
        metadata = dict(context.invocation_metadata())
        loop = asyncio.get_running_loop()
        grpc_conn = GrpcConnection(loop)

        try:
            session_id, session_role = await self._authenticate(metadata, grpc_conn, context)
        except ConnectionError:
            return

        ack = grpc_service_pb2.Message(  # type: ignore[attr-defined]
            id="",
            msg_type="auth_success",
            session_id=session_id,
            direction="response",
            content="authenticated",
        )
        yield grpc_service_pb2.BidirectionalStreamResponse(message=ack)  # type: ignore[attr-defined]

        receive_task = asyncio.create_task(self._receive_loop(request_iterator, session_id, session_role, grpc_conn))

        try:
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
                frame.command.CopyFrom(build_command_frame(data))
            elif action:
                self._set_control_frame(frame, data)
            else:
                frame.message.CopyFrom(build_message_frame(data))

            yield frame

    def _set_control_frame(self, frame: Any, data: dict[str, Any]) -> None:
        control_out = grpc_service_pb2.ControlMessage(  # type: ignore[attr-defined]
            action=data.get("action", ""),
            account_id=data.get("account_id", ""),
            room_id=data.get("room_id", ""),
            display_name=data.get("display_name", ""),
        )
        text = data.get("text")
        if text:
            control_out.text = text
        _set_proto_from_dict(control_out.identity, data.get("identity"), build_identity_frame)
        _set_proto_from_dict(control_out.profile, data.get("profile"), lambda v: {str(k): str(v) for k, v in v.items()})
        _set_proto_from_dict(
            control_out.metadata, data.get("metadata"), lambda v: {str(k): str(v) for k, v in v.items()}
        )
        frame.control.CopyFrom(control_out)

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
        self._session_manager.router.route_message(ack)

    async def _dispatch_message(self, msg_proto: Any, session_id: str, session_role: str) -> None:
        metadata = parse_message_metadata(msg_proto.metadata)
        account_id = metadata.get("account_id", "") or ""

        try:
            msg = Message(
                id=msg_proto.id,
                correlation_id=msg_proto.correlation_id or None,
                session_id=session_id,
                source_role=session_role,
                target_role=msg_proto.target_role or "*",
                account_id=account_id,
                direction=Direction(msg_proto.direction),
                msg_type=msg_proto.msg_type,
                content=msg_proto.content,
                content_type=msg_proto.content_type or "text/plain",
                state=msg_proto.state or None,
                metadata=metadata,
                speaker=parse_identity(msg_proto.speaker),
                room_id=msg_proto.room_id,
            )
        except Exception:
            logger.warning("GrpcServer: invalid message parse failed")
            return

        if not self._validate_session(session_id, msg.msg_type):
            return

        await asyncio.to_thread(self._on_message, msg)

        if not msg.metadata.get("ack_required", False):
            return
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
                display_name=control_proto.display_name,
                text=control_proto.text,
                identity=parse_identity(control_proto.identity),
                profile=dict(control_proto.profile),
                metadata=dict(control_proto.metadata),
            )
        except Exception:
            logger.warning("GrpcServer: invalid control message parse failed")
            return

        await asyncio.to_thread(self._on_control_message, control_msg, session_id, session_role)
