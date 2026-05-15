from __future__ import annotations

import logging
import threading
from multiprocessing.connection import Listener
from typing import Any

from iris.kernel.io.models import PIPE_NAME_OUTPUT, OutputMessage

from .session_manager import SessionManager

logger = logging.getLogger(__name__)


class OutputManager:
    """Kernel 側の出力管理。

    SessionManager を介してセッションに対応する Output 接続にメッセージをルーティングする。
    """

    def __init__(self, session_manager: SessionManager) -> None:
        self._session_manager = session_manager
        self._listener: Any = None
        self._running = False

    def start(self, pipe_address: str = PIPE_NAME_OUTPUT) -> None:
        self._listener = Listener(pipe_address, family="AF_PIPE")
        self._running = True
        t = threading.Thread(target=self._accept_loop, daemon=True, name="output-mgr-accept")
        t.start()
        logger.info("OutputManager listening on %s", pipe_address)

    def _accept_loop(self) -> None:
        while self._running:
            try:
                conn = self._listener.accept()
                raw = conn.recv_bytes()
                import json

                data = json.loads(raw.decode("utf-8"))
                session_id = data.get("session_id", "")

                if not session_id:
                    logger.warning("Output connection without session_id rejected")
                    conn.close()
                    continue

                success = self._session_manager.on_output_connect(session_id, conn)
                if success:
                    logger.info("OutputManager: session %s connected", session_id)
                else:
                    logger.warning("OutputManager: session %s connection rejected", session_id)
                    conn.close()
            except Exception:
                if self._running:
                    logger.exception("OutputManager accept failed")
                break

    def stop(self) -> None:
        self._running = False
        if self._listener is not None:
            self._listener.close()
        logger.info("OutputManager stopped")

    def send(self, message: OutputMessage) -> None:
        self._session_manager.route_output(message.session_id, message)
