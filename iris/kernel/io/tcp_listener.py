from __future__ import annotations

import json
import logging
import threading
from collections.abc import Callable
from multiprocessing.connection import Connection, Listener
from typing import Any

from iris.kernel.io.models import INPUT_MSG_TYPES, TCP_HOST, TCP_PORT, InputMessage

from .session_manager import SessionManager

logger = logging.getLogger(__name__)


class TcpListener:
    """TCP接続を1ポートで受け付け、メッセージ種別に応じてディスパッチする。

    1接続 = 1セッション。認証、入力、出力を単一のTCP接続で多重化。
    """

    def __init__(
        self,
        session_manager: SessionManager,
        on_input: Callable[[InputMessage], None] | None = None,
    ) -> None:
        self._session_manager = session_manager
        self._on_input = on_input or self._noop
        self._listener: Any = None
        self._running = False
        self._thread: threading.Thread | None = None

    def set_on_input(self, on_input: Callable[[InputMessage], None]) -> None:
        self._on_input = on_input

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
        from iris.kernel.io.models import AuthMessage

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
        from iris.kernel.io.models import PongMessage

        self._session_manager.update_activity(session_id)
        raw = PongMessage().model_dump_json().encode("utf-8")
        try:
            conn.send_bytes(raw)
        except (BrokenPipeError, ConnectionError, EOFError):
            logger.info("TcpListener: ping response failed, connection lost")
            if session_id:
                self._session_manager.remove_session(session_id)

    def _handle_input(self, data: dict[str, Any]) -> None:
        from iris.kernel.io.models import InputMessage

        msg = InputMessage(**data)
        session_id = msg.session_id
        if not session_id:
            logger.warning("TcpListener: InputMessage without session_id")
            return
        if not self._session_manager.is_session_active(session_id):
            logger.warning("TcpListener: InputMessage from inactive session: %s", session_id)
            return

        self._on_input(msg)

        if msg.metadata.get("ack_required", False):
            from iris.kernel.io.models import OutputMessage

            ack = OutputMessage(
                session_id=session_id,
                msg_type="ack",
                content=f"ack:{msg.id}",
                correlation_id=msg.id,
            )
            self._session_manager.route_output(session_id, ack)
