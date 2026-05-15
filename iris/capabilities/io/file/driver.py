from __future__ import annotations

import logging
from pathlib import Path

from iris.kernel.io.models import OutputMessage
from iris.kernel.io.protocols import OutputDriver

logger = logging.getLogger(__name__)


class FileOutputDriver(OutputDriver):
    driver_id = "file"
    description = "File output logging"
    features: set[str] = {"text"}

    def __init__(self, path: str = "iris_output.log") -> None:
        self._path = Path(path)
        self._running = False

    def start(self) -> None:
        self._running = True
        self._path.parent.mkdir(parents=True, exist_ok=True)
        logger.info("FileOutputDriver writing to %s", self._path)

    def stop(self) -> None:
        self._running = False

    def write(self, message: OutputMessage) -> None:
        if not self._running:
            return
        if message.msg_type == "stream":
            return
        timestamp = message.metadata.get("timestamp", "")
        prefix = f"[{timestamp}] " if timestamp else ""
        try:
            with self._path.open("a", encoding="utf-8") as f:
                f.write(f"{prefix}[{message.msg_type}] {message.content}\n")
        except OSError:
            logger.exception("FileOutputDriver write failed")

    def can_handle(self, destination: str) -> bool:
        return destination == self.driver_id or destination == "*"


def register(registry: object) -> None:
    from iris.capabilities.registry import CapabilityRegistry

    if not isinstance(registry, CapabilityRegistry):
        return
    registry.register_driver(kind="output", driver_id="file", description="File output logging")
