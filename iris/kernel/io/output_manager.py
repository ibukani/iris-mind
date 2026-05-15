from __future__ import annotations

import logging
from multiprocessing.connection import Client
from typing import Any

from iris.kernel.io.models import PIPE_NAME_OUTPUT, OutputMessage

logger = logging.getLogger(__name__)


class OutputManager:
    def __init__(self) -> None:
        self._client: Any = None

    def start(self, pipe_address: str = PIPE_NAME_OUTPUT) -> None:
        self._client = Client(pipe_address, family="AF_PIPE")
        logger.info("OutputManager connected to %s", pipe_address)

    def stop(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None
        logger.info("OutputManager stopped")

    def send(self, message: OutputMessage) -> None:
        if self._client is None:
            logger.warning("OutputManager: not connected, dropping message")
            return
        raw = message.model_dump_json().encode("utf-8")
        try:
            self._client.send_bytes(raw)
        except (BrokenPipeError, ConnectionError, EOFError):
            logger.warning("OutputManager: connection lost")
            self._client = None
