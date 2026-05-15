from __future__ import annotations

import json
import logging
import threading
from multiprocessing.connection import Connection, Listener
from typing import Any

from iris.kernel.io.models import PIPE_NAME_CONTROL, AuthMessage

from .session_manager import SessionManager

logger = logging.getLogger(__name__)


class ControlListener:
    """制御パイプの管理。

    認証ハンドシェイク、セッション管理、制御メッセージの処理を担当。
    """

    def __init__(self, session_manager: SessionManager) -> None:
        self._session_manager = session_manager
        self._listener: Any = None
        self._running = False
        self._thread: threading.Thread | None = None

    def start(self, pipe_address: str = PIPE_NAME_CONTROL) -> None:
        self._listener = Listener(pipe_address, family="AF_PIPE")
        self._running = True
        self._thread = threading.Thread(target=self._accept_loop, daemon=True, name="control-manager")
        self._thread.start()
        logger.info("ControlListener started on %s", pipe_address)

    def stop(self) -> None:
        self._running = False
        if self._listener is not None:
            self._listener.close()
        logger.info("ControlListener stopped")

    def _accept_loop(self) -> None:
        listener = self._listener
        assert listener is not None
        while self._running:
            try:
                conn: Connection = listener.accept()
                logger.info("ControlListener: connection accepted")
                t = threading.Thread(target=self._serve, args=(conn,), daemon=True)
                t.start()
            except Exception:
                if self._running:
                    logger.exception("ControlListener accept failed")
                break

    def _serve(self, conn: Connection) -> None:
        try:
            raw = conn.recv_bytes()
            data = json.loads(raw.decode("utf-8"))
            msg = AuthMessage(**data)

            response = self._session_manager.on_control_connect(conn, msg)
            response_raw = response.model_dump_json().encode("utf-8")
            conn.send_bytes(response_raw)

            if response.msg_type == "auth_failure":
                conn.close()
                logger.info("ControlListener: auth failed, connection closed")
                return

            logger.info("ControlListener: auth successful, keeping connection open")

        except (EOFError, ConnectionError, BrokenPipeError):
            logger.info("ControlListener: connection closed")
        except Exception:
            if self._running:
                logger.exception("ControlListener serve error")
