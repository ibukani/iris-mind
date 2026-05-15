from __future__ import annotations

import logging
import threading
from multiprocessing.connection import Listener
from typing import Any

from iris.kernel.io.models import PIPE_NAME_OUTPUT, OutputMessage

logger = logging.getLogger(__name__)


class OutputManager:
    """Kernel 側の出力管理。Named Pipe の Listener（サーバー）として起動し、
    Output Process の接続を待つ。"""

    def __init__(self) -> None:
        self._listener: Any = None
        self._conn: Any = None
        self._lock = threading.Lock()

    def start(self, pipe_address: str = PIPE_NAME_OUTPUT) -> None:
        self._listener = Listener(pipe_address, family="AF_PIPE")
        t = threading.Thread(target=self._accept, daemon=True, name="output-mgr-accept")
        t.start()
        logger.info("OutputManager listening on %s", pipe_address)

    def _accept(self) -> None:
        try:
            conn = self._listener.accept()
            with self._lock:
                self._conn = conn
            logger.info("OutputManager: Output Process connected")
        except Exception:
            if self._listener is not None:
                logger.exception("OutputManager accept failed")

    def stop(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None
            if self._listener is not None:
                self._listener.close()
                self._listener = None
        logger.info("OutputManager stopped")

    def send(self, message: OutputMessage) -> None:
        with self._lock:
            conn = self._conn
        if conn is None:
            logger.warning("OutputManager: not connected, dropping message")
            return
        raw = message.model_dump_json().encode("utf-8")
        try:
            conn.send_bytes(raw)
        except (BrokenPipeError, ConnectionError, EOFError):
            logger.warning("OutputManager: connection lost")
            with self._lock:
                self._conn = None
