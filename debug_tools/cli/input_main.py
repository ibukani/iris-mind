from __future__ import annotations

import logging
import sys
from multiprocessing.connection import Client

from iris.kernel.io.models import InputMessage

logger = logging.getLogger(__name__)

PIPE_NAME_KERNEL_INPUT = r"\\.\pipe\iris-kernel-input"


def main() -> None:
    pipe_address = sys.argv[1] if len(sys.argv) > 1 else PIPE_NAME_KERNEL_INPUT

    try:
        conn = Client(pipe_address, family="AF_PIPE")
        logger.info("Input Process connected to %s", pipe_address)
    except (ConnectionError, FileNotFoundError, OSError) as e:
        logger.error("Failed to connect to Kernel: %s", e)
        return

    try:
        while True:
            try:
                text = input()
            except (EOFError, KeyboardInterrupt):
                break
            if text is None:
                break
            if not text.strip():
                continue
            if text.lower() in ("exit", "quit"):
                break
            msg = InputMessage(
                source="cli",
                content=text,
                msg_type="command" if text.startswith("/") else "text",
            )
            try:
                conn.send_bytes(msg.model_dump_json().encode("utf-8"))
            except (BrokenPipeError, ConnectionError, EOFError) as e:
                logger.info("Connection to Kernel lost: %s", e)
                break
    except KeyboardInterrupt:
        logger.info("Input Process: shutting down")
    finally:
        conn.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
