"""
Input Process — 入力処理を担当する独立プロセス。

キーボード入力を受け付け、Named Pipe 経由で Kernel プロセスに送信する。

使用方法:
    python -m adapters.cli.input_main [<pipe_address>]
"""

from __future__ import annotations

import logging
import sys
import time
from datetime import datetime

from iris.kernel.ipc import PIPE_NAME_KERNEL_INPUT, PipeClient

logger = logging.getLogger(__name__)


def main() -> None:
    pipe_address = sys.argv[1] if len(sys.argv) > 1 else PIPE_NAME_KERNEL_INPUT

    while True:
        try:
            client = PipeClient(pipe_address)
            logger.info("Input Process connected to %s", pipe_address)
            _input_loop(client)
        except (EOFError, ConnectionError, BrokenPipeError, OSError):
            logger.warning("Input Process: connection lost, retrying in 2s...")
            time.sleep(2)
        except KeyboardInterrupt:
            logger.info("Input Process: shutting down")
            break


def _input_loop(client: PipeClient) -> None:
    from iris.kernel.event import UserInputEvent

    while True:
        try:
            text = input(">>> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not text:
            continue
        if text.lower() in ("exit", "quit"):
            break

        client.send(
            UserInputEvent(
                timestamp=datetime.now(),
                source="user_input",
                content=text,
            )
        )


if __name__ == "__main__":
    main()
