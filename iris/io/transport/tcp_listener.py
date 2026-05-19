from __future__ import annotations

from collections.abc import Callable
import json
import logging
from multiprocessing.connection import Connection, Listener
import threading
from typing import Any

from iris.io.models import (
    TCP_HOST,
    TCP_PORT,
    CommandInput,
    Direction,
    Message,
)
from iris.io.session.manager import SessionManager

logger = logging.getLogger(__name__)


class TcpListener:
    """TCP接続を1ポートで受け付け、メッセージ種別に応じてディスパッチする (v2.0)。"""

    def __init__(
        self,
        session_manager: SessionManager,
        on_message: Callable[[Message], None] | None = None,
        on_command: Callable[[CommandInput], None] | None = None,
    ) -> None:
        self._session_manager = session_manager
        self._on_message = on_message or self._noop
        self._on_command = on_command
        self._listener: Listener | None = None
        self._running = False
        self._thread: threading.Thread | None = None

    def set_on_message(self, on_message: Callable[[Message], None]) -> None:
        self._on_message = on_message

    def set_on_command(self, on_command: Callable[[CommandInput], None]) -> None:
        self._on_command = on_command

    @staticmethod
    def _noop(_msg: Message) -> None:
        return

    def start(self, host: str = TCP_HOST, port: int = TCP_PORT) -> None:
        self._listener = Listener((host, port), family="AF_INET")
        self._running = True
        self._thread = threading.Thread(target=self._accept_loop, daemon=True, name="tcp-listener")
        self._thread.start()
        logger.info("TcpListener started on %s:%d", host, port)

    def stop(self) -> None:
        self._running = False
        if self._listener is not None:
            self._listener.close()
        if self._thread is not None:
            self._thread.join(timeout=3)
            self._thread = None
        logger.info("TcpListener stopped")

    def _accept_loop(self) -> None:
        listener = self._listener
        assert listener is not None
        while self._running:
            try:
                conn: Connection = listener.accept()
                logger.info("TcpListener: connection accepted")
                t = threading.Thread(target=self._serve, args=(conn,), daemon=True)
                t.start()
            except Exception:
                if self._running:
                    logger.exception("TcpListener accept failed")
                break

    def _serve(self, conn: Connection) -> None:
        auth_done = False
        session_id: str | None = None
        session_role: str = "external"
        try:
            while self._running:
                raw = conn.recv_bytes()
                data: dict[str, Any] = json.loads(raw.decode("utf-8"))
                mt: str = data.get("msg_type", "")
                logger.debug(
                    "TcpListener: recv msg_type=%s data_keys=%s raw_bytes=%d",
                    mt,
                    list(data.keys()),
                    len(raw),
                )

                if mt == "auth":
                    if auth_done:
                        logger.warning("TcpListener: duplicate auth, ignoring")
                        continue
                    result = self._handle_auth(conn, data)
                    if result is None:
                        return
                    session_id, session_role = result
                    auth_done = True
                    continue

                if not auth_done:
                    logger.warning("TcpListener: message before auth, ignoring")
                    continue

                if mt == "ping":
                    self._handle_ping(conn, session_id)
                    continue

                if mt == "command":
                    self._session_manager.update_activity(session_id)
                    self._handle_command(data, session_role)
                    continue

                self._session_manager.update_activity(session_id)
                self._dispatch_message(data, session_role)

        except (EOFError, ConnectionError, BrokenPipeError):
            logger.info("TcpListener: connection closed")
            if session_id:
                self._session_manager.remove_session(session_id)
        except Exception:
            if self._running:
                logger.exception("TcpListener serve error")
                if session_id:
                    self._session_manager.remove_session(session_id)

    def _handle_auth(self, conn: Connection, data: dict[str, Any]) -> tuple[str, str] | None:
        from iris.io.models import AuthMessage

        msg = AuthMessage(**data)
        response = self._session_manager.authenticate(conn, msg)
        response_raw = response.model_dump_json().encode("utf-8")
        conn.send_bytes(response_raw)
        if response.msg_type == "auth_failure":
            logger.info("TcpListener: auth failed, closing connection")
            return None
        assert response.session_id is not None
        logger.info("TcpListener: session %s authenticated (role=%s)", response.session_id, msg.role)
        return response.session_id, msg.role or "external"

    def _handle_ping(self, conn: Connection, session_id: str | None) -> None:
        from iris.io.models import PongMessage

        logger.debug("TcpListener: ping session=%s", session_id)
        self._session_manager.update_activity(session_id)
        raw = PongMessage().model_dump_json().encode("utf-8")
        try:
            conn.send_bytes(raw)
            logger.debug("TcpListener: pong sent session=%s", session_id)
        except (BrokenPipeError, ConnectionError, EOFError):
            logger.info("TcpListener: ping response failed, connection lost")
            if session_id:
                self._session_manager.remove_session(session_id)

    def _dispatch_message(self, data: dict[str, Any], session_role: str) -> None:
        from pydantic import ValidationError

        try:
            msg = Message(**data)
        except (ValidationError, Exception):
            logger.warning(
                "TcpListener: invalid Message (unknown direction or bad data), ignoring: keys=%s",
                list(data.keys()),
            )
            return
        msg.source_role = session_role
        msg.session_id = msg.session_id or ""

        if not msg.session_id:
            logger.warning("TcpListener: Message without session_id, ignoring")
            return
        if not self._session_manager.is_session_active(msg.session_id):
            logger.warning("TcpListener: Message from inactive session: %s", msg.session_id)
            return
        if not self._session_manager.check_send_permission(msg.session_id, msg.msg_type):
            logger.warning(
                "TcpListener: session=%s lacks permission for msg_type=%s",
                msg.session_id,
                msg.msg_type,
            )
            err = Message(
                msg_type="error",
                content=f"Permission denied: cannot send {msg.msg_type}",
                source_role="mind",
                target_role=session_role,
                session_id=msg.session_id,
                direction=Direction.RESPONSE,
            )
            self._session_manager.route_message(err)
            return

        truncated = msg.content[:200] + "..." if len(msg.content) > 200 else msg.content
        logger.debug(
            "TcpListener: message dispatch id=%s session=%s dir=%s type=%s source=%s target=%s content=%.200s",
            msg.id,
            msg.session_id,
            msg.direction.value if isinstance(msg.direction, Direction) else msg.direction,
            msg.msg_type,
            msg.source_role,
            msg.target_role,
            truncated,
        )

        self._on_message(msg)

        if msg.metadata.get("ack_required", False):
            ack = Message(
                msg_type="ack",
                content=f"ack:{msg.id}",
                correlation_id=msg.id,
                source_role="mind",
                target_role=session_role,
                session_id=msg.session_id,
                direction=Direction.RESPONSE,
            )
            self._session_manager.route_message(ack)

    def _handle_command(self, data: dict[str, Any], session_role: str) -> None:
        msg = CommandInput(**data)
        msg.source_role = session_role
        if not msg.session_id:
            logger.warning("TcpListener: CommandInput without session_id")
            return
        if not self._session_manager.is_session_active(msg.session_id):
            logger.warning("TcpListener: CommandInput from inactive session: %s", msg.session_id)
            return
        if not self._session_manager.check_send_permission(msg.session_id, "command"):
            logger.warning(
                "TcpListener: session=%s lacks permission to send command",
                msg.session_id,
            )
            return

        logger.debug(
            "TcpListener: command dispatch id=%s session=%s role=%s content=%.200s",
            msg.id,
            msg.session_id,
            msg.source_role,
            msg.content,
        )
        if self._on_command:
            self._on_command(msg)
