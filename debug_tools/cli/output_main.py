"""
Output Process — 表示処理を担当する独立プロセス。

Kernel プロセスから Named Pipe 経由でイベントを受信し、
Renderer を使ってターミナル表示する。

Pipe 切断時は再接続を試みず、終了する。

使用方法:
    python -m debug_tools.cli.output_main [<pipe_address>]
"""

from __future__ import annotations

import logging
import sys

from iris.kernel.ipc import PIPE_NAME_KERNEL_OUTPUT, PipeClient

from .renderer import Renderer

logger = logging.getLogger(__name__)


def main() -> None:
    pipe_address = sys.argv[1] if len(sys.argv) > 1 else PIPE_NAME_KERNEL_OUTPUT
    renderer = Renderer()

    while True:
        try:
            client = PipeClient(pipe_address)
            logger.info("Output Process connected to %s", pipe_address)
            while True:
                event = client.recv()
                renderer.handle(event)
        except (EOFError, ConnectionError, BrokenPipeError, OSError):
            logger.info("Output Process: connection lost")
            break
        except KeyboardInterrupt:
            logger.info("Output Process: shutting down")
            break


if __name__ == "__main__":
    main()
