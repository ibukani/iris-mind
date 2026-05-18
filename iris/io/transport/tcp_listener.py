from __future__ import annotations

from collections.abc import Callable
import json
import logging
from multiprocessing.connection import Connection, Listener
import threading
from typing import Any

from iris.io.models import (
    INPUT_MSG_TYPES,
    TCP_HOST,
    TCP_PORT,
    CommandInput,
    InputMessage,
    InterruptMessage,
    OutputMessage,
)
from iris.io.session.manager import SessionManager

logger = logging.getLogger(__name__)


class TcpListener:
    """TCP接続を1ポートで受け付け、メッセージ種別に応じてディスパッチする。"""

    def __init__(
        self,
        session_manager: SessionManager,
        on_input: Callable[[InputMessage], None] | None = None,
        on_command: Callable[[CommandInput], None] | None = None,
        on_interrupt: Callable[[str], None] | None = None,
    ) -> None:
        self._session_manager = session_manager
        self._on_input = on_input or self._noop
        self._on_command = on_command
        self._on_interrupt = on_interrupt
        self._listener: Listener | None = None
        self._running = False
        self._thread: threading.Thread | None = None

    def set_on_input(self, on_input: Callable[[InputMessage], None]) -> None:
        self._on_input = on_input

    def set_on_command(self, on_command: Callable[[CommandInput], None]) -> None:
        self._on_command = on_command

    def set_on_interrupt(self, on_interrupt: Callable[[str], None]) -> None:
        self._on_interrupt = on_interrupt

    @staticmethod
    def _noop(_msg: InputMessage) -> None:
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
                    sid = self._handle_auth(conn, data)
                    if sid is None:
                        return
                    session_id = sid
                    auth_done = True
                    continue

                if not auth_done:
                    logger.warning("TcpListener: message before auth, ignoring")
                    continue

                if mt == "ping":
                    self._handle_ping(conn, session_id)
                    continue

                if mt == "interrupt":
                    im = InterruptMessage(**data)
                    logger.debug("TcpListener: interrupt session=%s", im.session_id)
                    if self._on_interrupt:
                        self._on_interrupt(im.session_id)
                    continue

                if mt in "command":
                    self._session_manager.update_activity(session_id)
                    self._handle_command(data)
                    continue

                if mt in INPUT_MSG_TYPES:
                    self._session_manager.update_activity(session_id)
                    self._handle_input(data)
                    continue

                logger.debug("TcpListener: unknown msg_type=%s, ignoring", mt)

        except (EOFError, ConnectionError, BrokenPipeError):
            logger.info("TcpListener: connection closed")
            if session_id:
                self._session_manager.remove_session(session_id)
        except Exception:
            if self._running:
                logger.exception("TcpListener serve error")
                if session_id:
                    self._session_manager.remove_session(session_id)

    def _handle_auth(self, conn: Connection, data: dict[str, Any]) -> str | None:
        from iris.io.models import AuthMessage

        msg = AuthMessage(**data)
        response = self._session_manager.authenticate(conn, msg)
        response_raw = response.model_dump_json().encode("utf-8")
        conn.send_bytes(response_raw)
        if response.msg_type == "auth_failure":
            logger.info("TcpListener: auth failed, closing connection")
            return None
        logger.info("TcpListener: session %s authenticated", response.session_id)
        return response.session_id

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

    def _handle_input(self, data: dict[str, Any]) -> None:
        msg = InputMessage(**data)
        session_id = msg.session_id
        if not session_id:
            logger.warning("TcpListener: InputMessage without session_id")
            return
        if not self._session_manager.is_session_active(session_id):
            logger.warning("TcpListener: InputMessage from inactive session: %s", session_id)
            return

        truncated = msg.content[:200] + "..." if len(msg.content) > 200 else msg.content
        logger.debug(
            "TcpListener: input dispatch id=%s session=%s type=%s final=%s content=%.200s",
            msg.id,
            session_id,
            msg.msg_type,
            msg.is_final,
            truncated,
        )
        self._on_input(msg)

        if msg.metadata.get("ack_required", False):
            ack = OutputMessage(
                msg_type="ack",
                content=f"ack:{msg.id}",
                correlation_id=msg.id,
            )
            self._session_manager.route_output(session_id, ack)

    def _handle_command(self, data: dict[str, Any]) -> None:
        msg = CommandInput(**data)
        session_id = msg.session_id
        if not session_id:
            logger.warning("TcpListener: CommandInput without session_id")
            return
        if not self._session_manager.is_session_active(session_id):
            logger.warning("TcpListener: CommandInput from inactive session: %s", session_id)
            return

        logger.debug(
            "TcpListener: command dispatch id=%s session=%s content=%.200s",
            msg.id,
            session_id,
            msg.content,
        )
        if self._on_command:
            self._on_command(msg)
