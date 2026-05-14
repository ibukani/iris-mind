"""
Input Process — 入力処理を担当する独立プロセス。

キーボード入力を受け付け、Named Pipe 経由で Kernel プロセスに送信する。

Pipe 切断時は再接続を試みず、終了する。
Supervisor によるシャットダウン時は Thread + Queue 方式で input() ブロッキングを解除する。

使用方法:
    python -m debug_tools.cli.input_main [<pipe_address>]
"""

from __future__ import annotations

import logging
import queue
import sys
import threading
from collections.abc import Callable
from datetime import datetime

from iris.kernel.ipc import PIPE_NAME_KERNEL_INPUT, PipeClient

logger = logging.getLogger(__name__)


def main() -> None:
    pipe_address = sys.argv[1] if len(sys.argv) > 1 else PIPE_NAME_KERNEL_INPUT
    running = True

    while running:
        try:
            client = PipeClient(pipe_address)
            logger.info("Input Process connected to %s", pipe_address)
            _input_loop(client, lambda: running)
        except (EOFError, ConnectionError, BrokenPipeError, OSError):
            logger.info("Input Process: connection lost")
            break
        except KeyboardInterrupt:
            logger.info("Input Process: shutting down")
            break


def _input_loop(client: PipeClient, is_running: Callable[[], bool]) -> None:
    from iris.kernel.event import UserInputEvent

    q: queue.Queue[str | None] = queue.Queue()

    def _reader() -> None:
        try:
            while is_running():
                try:
                    text = input()
                    q.put(text)
                except (EOFError, KeyboardInterrupt):
                    q.put(None)
                    break
        except Exception:
            q.put(None)

    thread = threading.Thread(target=_reader, daemon=True)
    thread.start()

    while is_running():
        try:
            text = q.get(timeout=0.5)
        except queue.Empty:
            continue
        if text is None:
            break
        if not text.strip():
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
