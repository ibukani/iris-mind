from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager


class PriorityLock:
    """優先度付きの非同期排他ロック。

    優先度（小さい数値ほど高い優先度）に応じてロックを獲得する。
    デフォルトは priority=0 (高)。バックグラウンド処理は priority=1 (低) を指定する。
    """

    def __init__(self) -> None:
        self._locked = False
        # (priority, sequence_number, event) のタプルを保持
        self._waiters: asyncio.PriorityQueue[tuple[int, int, asyncio.Event]] = asyncio.PriorityQueue()
        self._seq = 0

    async def acquire(self, priority: int = 0) -> None:
        if not self._locked and self._waiters.empty():
            self._locked = True
            return

        event = asyncio.Event()
        self._seq += 1
        await self._waiters.put((priority, self._seq, event))
        await event.wait()
        # イベントが発火した時点でロックを獲得した状態になる

    def release(self) -> None:
        if not self._locked:
            msg = "Lock is not acquired."
            raise RuntimeError(msg)

        if self._waiters.empty():
            self._locked = False
            return

        # 次の待機者を起こす。起こした待機者が次のロック保持者となる。
        _, _, event = self._waiters.get_nowait()
        event.set()

    @asynccontextmanager
    async def __call__(self, priority: int = 0) -> AsyncGenerator[None]:
        await self.acquire(priority)
        try:
            yield
        finally:
            self.release()
