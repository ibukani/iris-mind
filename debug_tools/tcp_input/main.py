"""
TCP Input Adapter — TCP ソケット経由で Iris に入力を送信する。

使用方法:
    python -m adapters.tcp_input.main [<port>] [<pipe_address>]

外部から telnet や curl で接続:
    echo "hello" | nc localhost 9876
    telnet localhost 9876
"""

from __future__ import annotations

import logging
import socket
import sys
import threading
import time
from datetime import datetime

from iris.kernel.ipc import PIPE_NAME_KERNEL_INPUT, PipeClient

logger = logging.getLogger(__name__)

DEFAULT_PORT = 9876


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PORT
    pipe_address = sys.argv[2] if len(sys.argv) > 2 else PIPE_NAME_KERNEL_INPUT

    client = _connect_to_kernel(pipe_address)

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", port))
    server.listen(5)
    logger.info("TCP Input Adapter listening on 127.0.0.1:%d", port)
    logger.info("Connect to Kernel at %s", pipe_address)

    try:
        while True:
            conn, addr = server.accept()
            logger.info("TCP connection from %s:%d", addr[0], addr[1])
            t = threading.Thread(
                target=_handle_tcp_conn,
                args=(conn, addr, client),
                daemon=True,
            )
            t.start()
    except KeyboardInterrupt:
        logger.info("TCP Input Adapter shutting down")
    finally:
        server.close()
        client.close()


def _connect_to_kernel(pipe_address: str, retries: int = 5, delay: float = 2.0) -> PipeClient:
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            return PipeClient(pipe_address)
        except (ConnectionError, FileNotFoundError, OSError) as e:
            last_error = e
            if attempt < retries - 1:
                logger.warning("Retrying connection to Kernel (%d/%d)...", attempt + 1, retries)
                time.sleep(delay)
    logger.error("Failed to connect to Kernel at %s after %d retries", pipe_address, retries)
    raise last_error if last_error else ConnectionError(f"Could not connect to {pipe_address}")


def _handle_tcp_conn(conn: socket.socket, addr: tuple[str, int], client: PipeClient) -> None:
    from iris.kernel.event import UserInputEvent

    try:
        with conn:
            conn.sendall(b"Iris TCP Input Adapter\n")
            buffer = b""
            while True:
                data = conn.recv(4096)
                if not data:
                    break
                buffer += data
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    text = line.decode("utf-8", errors="replace").strip()
                    if text:
                        client.send(
                            UserInputEvent(
                                timestamp=datetime.now(),
                                source=f"tcp:{addr[0]}:{addr[1]}",
                                content=text,
                            )
                        )
                        logger.debug("TCP input from %s: %s", addr[0], text)
    except (ConnectionError, OSError):
        logger.debug("TCP connection from %s closed", addr[0])


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
