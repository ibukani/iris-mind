import asyncio

import pytest

from iris.llm.priority_lock import PriorityLock


@pytest.mark.anyio
async def test_priority_lock_order():
    lock = PriorityLock()
    order = []

    # 初期のロックを獲得しておく（他のタスクを待機させるため）
    await lock.acquire(priority=0)

    async def worker(task_id: int, priority: int):
        async with lock(priority=priority):
            order.append(task_id)

    # 優先度1、0、2のタスクを並行起動（順序はバラバラ）
    tasks = [
        asyncio.create_task(worker(1, priority=1)),
        asyncio.create_task(worker(0, priority=0)),
        asyncio.create_task(worker(2, priority=2)),
    ]

    # タスクがキューに入るのを少し待つ
    await asyncio.sleep(0.01)

    # 最初のロックを解放（これにより待機中のタスクが優先度順に実行されるはず）
    lock.release()
    await asyncio.gather(*tasks)

    # priority=0 -> priority=1 -> priority=2 の順序で実行されるはず
    assert order == [0, 1, 2]
