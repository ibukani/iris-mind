from __future__ import annotations

import json
import logging
import threading
from multiprocessing.connection import Connection, Listener
from typing import Any

from iris.kernel.io.models import PIPE_NAME_OUTPUT, OutputMessage

from .session_manager import SessionManager

logger = logging.getLogger(__name__)


class OutputListener:
    """Kernel 側の出力管理。

    Named Pipe 経由で Output 接続を受け付け、SessionManager と紐付ける。
    送信メッセージは SessionManager を介して対応する接続にルーティングされる。
    """

    def __init__(self, session_manager: SessionManager) -> None:
        self._session_manager = session_manager
        self._pipe_address: str | None = None
        self._listener: Any = None
        self._running = False
        self._thread: threading.Thread | None = None

    def start(self, pipe_address: str = PIPE_NAME_OUTPUT) -> None:
        self._pipe_address = pipe_address
        self._listener = Listener(pipe_address, family="AF_PIPE")
        self._running = True
        self._thread = threading.Thread(target=self._accept_loop, daemon=True, name="output-manager")
        self._thread.start()
        logger.info("OutputListener started on %s", self._pipe_address)

    def stop(self) -> None:
        self._running = False
        if self._listener is not None:
            self._listener.close()
        if self._thread is not None:
            self._thread.join(timeout=3)
            self._thread = None
        logger.info("OutputListener stopped")

    def send(self, message: OutputMessage) -> None:
        self._session_manager.route_output(message.session_id, message)

    def _accept_loop(self) -> None:
        listener = self._listener
        assert listener is not None
        while self._running:
            try:
                conn: Connection = listener.accept()
                logger.info("OutputListener: connection accepted")
                t = threading.Thread(target=self._serve, args=(conn,), daemon=True)
                t.start()
            except Exception:
                if self._running:
                    logger.exception("OutputListener accept failed")
                break

    def _serve(self, conn: Connection) -> None:
        try:
            raw = conn.recv_bytes()
            data = json.loads(raw.decode("utf-8"))
            session_id = data.get("session_id", "")

            if not session_id:
                logger.warning("Output connection without session_id rejected")
                conn.close()
                return

            success = self._session_manager.on_output_connect(session_id, conn)
            if success:
                logger.info("OutputListener: session %s connected", session_id)
            else:
                logger.warning("OutputListener: session %s connection rejected", session_id)
                conn.close()

        except (EOFError, ConnectionError, BrokenPipeError):
            logger.info("OutputListener: connection closed")
        except Exception:
            if self._running:
                logger.exception("OutputListener serve error")
