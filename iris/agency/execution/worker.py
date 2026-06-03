from __future__ import annotations

import asyncio
import queue
import threading
from typing import Any

from loguru import logger


class AsyncWorker:
    """スレッド + asyncio イベントループ + キュー駆動の汎用ワーカー基底。

    サブクラスは ``async def process(self, item: Any) -> None`` を実装する。
    停止シグナルは ``None`` をキューに投入する (shutdown() が行う)。
    """

    def __init__(self, name: str = "async-worker") -> None:
        self._loop = asyncio.new_event_loop()
        self._queue: queue.Queue[Any | None] = queue.Queue()
        self._thread = threading.Thread(target=self._run, daemon=True, name=name)
        self._thread.start()

    def enqueue(self, item: Any) -> None:
        self._queue.put(item)

    async def process(self, item: Any) -> None:
        """Override in subclass."""

    def shutdown(self, timeout: float = 5.0) -> None:
        self._queue.put(None)
        self._thread.join(timeout=timeout)
        if self._thread.is_alive():
            logger.warning(
                "{} worker thread did not finish within {}s timeout",
                type(self).__name__,
                timeout,
            )
        self._loop.close()

    def _run(self) -> None:
        asyncio.set_event_loop(self._loop)
        while True:
            item = self._queue.get()
            if item is None:
                break
            try:
                self._loop.run_until_complete(self.process(item))
            except Exception:
                logger.exception(
                    "{}: process failed for {}",
                    type(self).__name__,
                    type(item).__name__,
                )
