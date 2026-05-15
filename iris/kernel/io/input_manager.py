from __future__ import annotations

import json
import logging
import threading
from collections.abc import Callable
from multiprocessing.connection import Connection, Listener
from typing import Any

from iris.kernel.io.models import PIPE_NAME_INPUT, InputMessage

logger = logging.getLogger(__name__)


class InputManager:
    def __init__(
        self,
        on_input: Callable[[InputMessage], None] | None = None,
    ) -> None:
        self._on_input = on_input or self._noop
        self._pipe_address: str | None = None
        self._listener: Any = None
        self._running = False
        self._thread: threading.Thread | None = None

    def set_on_input(self, on_input: Callable[[InputMessage], None]) -> None:
        self._on_input = on_input

    @staticmethod
    def _noop(_msg: InputMessage) -> None:
        return

    def start(self, pipe_address: str = PIPE_NAME_INPUT) -> None:
        self._pipe_address = pipe_address
        self._listener = Listener(pipe_address, family="AF_PIPE")
        self._running = True
        self._thread = threading.Thread(target=self._accept_loop, daemon=True, name="input-manager")
        self._thread.start()
        logger.info("InputManager started on %s", self._pipe_address)

    def stop(self) -> None:
        self._running = False
        if self._listener is not None:
            self._listener.close()
        logger.info("InputManager stopped")

    def _accept_loop(self) -> None:
        listener = self._listener
        assert listener is not None
        while self._running:
            try:
                conn: Connection = listener.accept()
                logger.info("InputManager: connection accepted")
                t = threading.Thread(target=self._serve, args=(conn,), daemon=True)
                t.start()
            except Exception:
                if self._running:
                    logger.exception("InputManager accept failed")
                break

    def _serve(self, conn: Connection) -> None:
        try:
            while self._running:
                raw = conn.recv_bytes()
                data = json.loads(raw.decode("utf-8"))
                msg = InputMessage(**data)
                self._on_input(msg)
        except (EOFError, ConnectionError, BrokenPipeError):
            logger.info("InputManager: connection closed")
        except Exception:
            if self._running:
                logger.exception("InputManager serve error")
