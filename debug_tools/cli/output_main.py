from __future__ import annotations

import json
import logging
import sys
from multiprocessing.connection import Client

from iris.kernel.io.models import PIPE_NAME_OUTPUT as PIPE_NAME_KERNEL_OUTPUT
from iris.kernel.io.models import OutputMessage

from .renderer import Renderer

logger = logging.getLogger(__name__)


def main() -> None:
    pipe_address = sys.argv[1] if len(sys.argv) > 1 else PIPE_NAME_KERNEL_OUTPUT
    renderer = Renderer()

    try:
        conn = Client(pipe_address, family="AF_PIPE")
        logger.info("Output Process connected to %s", pipe_address)
    except (ConnectionError, FileNotFoundError, OSError) as e:
        logger.error("Failed to connect to Kernel: %s", e)
        return

    try:
        while True:
            try:
                raw = conn.recv_bytes()
                data = json.loads(raw.decode("utf-8"))
                message = OutputMessage(**data)
                renderer.handle(message)
            except (EOFError, ConnectionError, BrokenPipeError, OSError):
                logger.info("Output Process: connection lost")
                break
    except KeyboardInterrupt:
        logger.info("Output Process: shutting down")
    finally:
        conn.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
