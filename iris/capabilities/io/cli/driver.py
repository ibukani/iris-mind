from __future__ import annotations

import logging
import queue
import sys
import threading
from collections.abc import Callable

from iris.kernel.io.models import InputMessage, OutputMessage
from iris.kernel.io.protocols import InputDriver, OutputDriver

logger = logging.getLogger(__name__)


class CliInputDriver(InputDriver):
    driver_id = "cli"
    description = "CLI standard input"

    def __init__(self) -> None:
        self._handler: Callable[[InputMessage], None] | None = None
        self._running = False
        self._thread: threading.Thread | None = None

    def start(self, handler: Callable[[InputMessage], None]) -> None:
        self._handler = handler
        self._running = True
        self._thread = threading.Thread(target=self._read_loop, daemon=True, name="cli-input")
        self._thread.start()

    def stop(self) -> None:
        self._running = False

    def _read_loop(self) -> None:
        q: queue.Queue[str | None] = queue.Queue()

        def _reader() -> None:
            try:
                while self._running:
                    try:
                        line = input()
                        q.put(line)
                    except (EOFError, KeyboardInterrupt):
                        q.put(None)
                        break
            except Exception:
                q.put(None)

        t = threading.Thread(target=_reader, daemon=True)
        t.start()

        while self._running:
            try:
                line = q.get(timeout=0.5)
            except queue.Empty:
                continue
            if line is None:
                break
            if not line.strip():
                continue
            handler = self._handler
            if handler is not None:
                handler(
                    InputMessage(
                        source=self.driver_id,
                        content=line,
                        msg_type="command" if line.startswith("/") else "text",
                    )
                )


class CliOutputDriver(OutputDriver):
    driver_id = "cli"
    description = "CLI standard output"
    features: set[str] = {"text", "stream"}

    def __init__(self) -> None:
        self._running = False

    def start(self) -> None:
        self._running = True

    def stop(self) -> None:
        self._running = False

    def write(self, message: OutputMessage) -> None:
        if not self._running:
            return
        text = message.content
        if message.msg_type == "stream":
            if text:
                sys.stdout.write(text)
                sys.stdout.flush()
        else:
            if message.msg_type == "response":
                print(f"\n{text}")
            elif message.msg_type == "proactive":
                print(f"\n[Iris] {text}")
            elif message.msg_type == "error":
                print(f"\n[Error] {text}", file=sys.stderr)
            elif message.msg_type == "command":
                print(text)
            else:
                print(f"\n{text}")

    def can_handle(self, destination: str) -> bool:
        return destination == self.driver_id or destination == "*"


def register(registry: object) -> None:
    from iris.capabilities.registry import CapabilityRegistry

    if not isinstance(registry, CapabilityRegistry):
        return
    registry.register_driver(kind="input", driver_id="cli", description="CLI standard input")
    registry.register_driver(kind="output", driver_id="cli", description="CLI standard output")
