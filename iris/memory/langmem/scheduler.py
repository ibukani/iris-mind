"""MemoryPipelineScheduler — 抽出パイプラインを非同期実行するための薄いスケジューラ。

責務:
- ``MemoryManager.flush()`` の同期ホットパスから抽出処理を剥がす
- 同一 ``(account_id, room_id)`` に対する重複スケジュールを抑止 (最新タスクのみ残す)
- バックグラウンドタスクで例外が出ても呼び出し側には伝播しない
- 実行中のイベントループが無い (同期コンテキスト) 場合は ``None`` を返し、
  呼び出し側で同期実行にフォールバックする責務を負わせる

注: LangChain / LangGraph 等の重いランタイムを使うため、別スレッドではなく
asyncio の同一ループ上でバックグラウンド task としてスケジュールする。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import threading
import time
from typing import TYPE_CHECKING, Any

from loguru import logger

if TYPE_CHECKING:
    from iris.memory.langmem.pipeline import MemoryPipeline


@dataclass
class _ScheduledTask:
    """(account_id, room_id) 単位のスケジュール済みタスク情報。"""

    key: tuple[str, str]
    task: asyncio.Task[Any]
    created_at: float
    enqueued_count: int = 1


@dataclass
class SchedulerStats:
    """運用時に参照できる統計情報。"""

    active_tasks: int = 0
    total_scheduled: int = 0
    total_deduplicated: int = 0
    total_failed: int = 0
    last_error: str = ""
    last_error_pass: str = ""
    last_error_account: str = ""
    last_error_room: str = ""
    by_pass_count: dict[str, int] = field(default_factory=dict)


class MemoryPipelineScheduler:
    """``MemoryPipeline.run_full_cycle()`` / ``run_pass()`` をバックグラウンド化する。"""

    def __init__(self, pipeline: MemoryPipeline) -> None:
        self._pipeline = pipeline
        self._tasks: dict[tuple[str, str], _ScheduledTask] = {}
        # asyncio はシングルスレッドだが、``_schedule`` / ``_run`` の finally が
        # 別スレッド (ロック競合する sync caller) から呼ばれる可能性を考慮し、
        # dict 操作は ``_tasks_lock`` で直列化する。``asyncio.Lock`` は
        # shutdown 時の await が必要な区間のみに使用する。
        self._tasks_lock = threading.Lock()
        self._lock = asyncio.Lock()
        self._stats = SchedulerStats()

    @property
    def stats(self) -> SchedulerStats:
        """現在の統計情報スナップショットを返す。"""
        with self._tasks_lock:
            self._stats.active_tasks = sum(1 for t in self._tasks.values() if not t.task.done())
        return self._stats

    def is_already_running(self, account_id: str, room_id: str) -> bool:
        """指定スコープでタスクが実行中か否か。"""
        key = (account_id, room_id)
        with self._tasks_lock:
            st = self._tasks.get(key)
        return st is not None and not st.task.done()

    def schedule_full_cycle(
        self,
        *,
        account_id: str = "",
        room_id: str = "",
        source_record_ids: list[str] | None = None,
    ) -> asyncio.Task[Any] | None:
        """全パスを非同期に実行する。イベントループが無い / 登録済みなら None。"""
        return self._schedule(
            account_id=account_id,
            room_id=room_id,
            run_call=lambda: self._pipeline.run_full_cycle(
                source_record_ids=source_record_ids,
                account_id=account_id,
                room_id=room_id,
            ),
        )

    def schedule_pass(
        self,
        pass_type: Any,
        *,
        account_id: str = "",
        room_id: str = "",
        source_record_ids: list[str] | None = None,
    ) -> asyncio.Task[Any] | None:
        return self._schedule(
            account_id=account_id,
            room_id=room_id,
            run_call=lambda pt=pass_type: self._pipeline.run_pass(
                pt,
                source_record_ids=source_record_ids,
                account_id=account_id,
                room_id=room_id,
            ),
        )

    async def shutdown(self, *, cancel: bool = False) -> None:
        """実行中タスクの完了を待つ (必要ならキャンセル)。"""
        async with self._lock:
            with self._tasks_lock:
                pending = list(self._tasks.values())
                self._tasks.clear()
        for st in pending:
            if cancel:
                st.task.cancel()
        for st in pending:
            try:
                await st.task
            except (asyncio.CancelledError, Exception):
                logger.debug("MemoryPipelineScheduler.shutdown: task ended with exception")

    def _schedule(
        self,
        *,
        account_id: str,
        room_id: str,
        run_call: Any,
    ) -> asyncio.Task[Any] | None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.debug("MemoryPipelineScheduler: no running event loop, caller should fallback")
            return None

        key = (account_id, room_id)
        with self._tasks_lock:
            existing = self._tasks.get(key)
            if existing is not None and not existing.task.done():
                existing.enqueued_count += 1
                self._stats.total_deduplicated += 1
                logger.debug(
                    "MemoryPipelineScheduler: dedup account={} room={} pending_count={}",
                    account_id,
                    room_id,
                    existing.enqueued_count,
                )
                return None

            task = loop.create_task(
                self._run(account_id=account_id, room_id=room_id, run_call=run_call),
                name=f"MemoryPipelineScheduler[{account_id}:{room_id}]",
            )
            self._tasks[key] = _ScheduledTask(
                key=key,
                task=task,
                created_at=time.time(),
            )
            self._stats.total_scheduled += 1
        return task

    async def _run(
        self,
        *,
        account_id: str,
        room_id: str,
        run_call: Any,
    ) -> Any:
        try:
            return await asyncio.to_thread(run_call)
        except Exception as e:
            self._stats.total_failed += 1
            self._stats.last_error = repr(e)
            self._stats.last_error_account = account_id
            self._stats.last_error_room = room_id
            logger.exception(
                "MemoryPipelineScheduler: background run failed account={} room={}",
                account_id,
                room_id,
            )
            return None
        finally:
            # 完了 (成功/失敗/キャンセル) したタスクは登録から外す。
            with self._tasks_lock:
                st = self._tasks.get((account_id, room_id))
                if st is not None and st.task.done():
                    self._tasks.pop((account_id, room_id), None)


__all__ = ["MemoryPipelineScheduler", "SchedulerStats"]
