"""
Output Process — 表示処理を担当する独立プロセス。

Kernel プロセスから Named Pipe 経由でイベントを受信し、
Renderer を使ってターミナル表示する。

使用方法:
    python -m adapters.cli.output_main [<pipe_address>]
"""

from __future__ import annotations

import logging
import sys
import time

from iris.kernel.ipc import PIPE_NAME_KERNEL, PipeClient

from .renderer import Renderer

logger = logging.getLogger(__name__)


def main() -> None:
    pipe_address = sys.argv[1] if len(sys.argv) > 1 else PIPE_NAME_KERNEL
    renderer = Renderer()

    while True:
        try:
            client = PipeClient(pipe_address)
            logger.info("Output Process connected to %s", pipe_address)
            while True:
                event = client.recv()
                renderer.handle(event)
        except (EOFError, ConnectionError, BrokenPipeError, OSError):
            logger.warning("Output Process: connection lost, retrying in 2s...")
            time.sleep(2)
        except KeyboardInterrupt:
            logger.info("Output Process: shutting down")
            break


if __name__ == "__main__":
    main()
