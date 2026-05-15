from __future__ import annotations

import logging
import socket
import threading
from collections.abc import Callable

from iris.kernel.io.models import InputMessage
from iris.kernel.io.protocols import InputDriver

logger = logging.getLogger(__name__)


class TcpInputDriver(InputDriver):
    driver_id = "tcp"
    description = "TCP socket input"

    def __init__(self, port: int = 9876) -> None:
        self._port = port
        self._handler: Callable[[InputMessage], None] | None = None
        self._running = False
        self._thread: threading.Thread | None = None
        self._server: socket.socket | None = None

    def start(self, handler: Callable[[InputMessage], None]) -> None:
        self._handler = handler
        self._running = True
        self._server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server.bind(("127.0.0.1", self._port))
        self._server.listen(5)
        self._thread = threading.Thread(target=self._accept_loop, daemon=True, name="tcp-input")
        self._thread.start()
        logger.info("TcpInputDriver listening on 127.0.0.1:%d", self._port)

    def stop(self) -> None:
        self._running = False
        if self._server is not None:
            self._server.close()

    def _accept_loop(self) -> None:
        server = self._server
        assert server is not None
        while self._running:
            try:
                conn, addr = server.accept()
                logger.info("TcpInputDriver: connection from %s:%d", addr[0], addr[1])
                t = threading.Thread(
                    target=self._handle_conn,
                    args=(conn, addr),
                    daemon=True,
                )
                t.start()
            except OSError:
                if self._running:
                    logger.exception("TcpInputDriver accept failed")
                break

    def _handle_conn(self, conn: socket.socket, addr: tuple[str, int]) -> None:
        handler = self._handler
        if handler is None:
            return
        try:
            with conn:
                conn.sendall(b"Iris TCP Input\n")
                buf = b""
                while self._running:
                    data = conn.recv(4096)
                    if not data:
                        break
                    buf += data
                    while b"\n" in buf:
                        line, buf = buf.split(b"\n", 1)
                        text = line.decode("utf-8", errors="replace").strip()
                        if not text:
                            continue
                        handler(
                            InputMessage(
                                source=f"tcp:{addr[0]}:{addr[1]}",
                                content=text,
                            )
                        )
        except (ConnectionError, OSError):
            logger.debug("TcpInputDriver: connection from %s closed", addr[0])


def register(registry: object) -> None:
    from iris.capabilities.registry import CapabilityRegistry

    if not isinstance(registry, CapabilityRegistry):
        return
    registry.register_driver(kind="input", driver_id="tcp", description="TCP socket input")
