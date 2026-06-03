"""MemoryManager の ``_trigger_pipeline`` 経由のパイプラインディスパッチテスト。"""

from __future__ import annotations

from typing import Any

from iris.memory.langmem.scheduler import MemoryPipelineScheduler
from iris.memory.manager import MemoryManager


class _StubPipeline:
    enabled = True

    def __init__(self) -> None:
        self._config = type("Cfg", (), {"batch_min_turns": 1})()
        self.call_count = 0
        self.calls: list[dict[str, Any]] = []

    def run_full_cycle(self, **kwargs: Any) -> dict[str, list[Any]]:
        self.call_count += 1
        self.calls.append(kwargs)
        return {"semantic": []}


class _StubScheduler(MemoryPipelineScheduler):
    """イベントループ無しでも動かせるスタブ。"""

    def __init__(self, pipeline: _StubPipeline) -> None:
        self._pipeline = pipeline  # type: ignore[assignment]
        self.schedule_calls: list[tuple[str, str]] = []
        self._running: set[tuple[str, str]] = set()
        self._deferred: set[tuple[str, str]] = set()

    def is_already_running(self, account_id: str, room_id: str) -> bool:
        return (account_id, room_id) in self._running

    def schedule_full_cycle(
        self,
        *,
        account_id: str = "",
        room_id: str = "",
        source_record_ids: list[str] | None = None,
    ) -> None:
        self.schedule_calls.append((account_id, room_id))
        return  # イベントループ無しを想定


class _AlwaysRunningScheduler(MemoryPipelineScheduler):
    def __init__(self) -> None:
        pass

    def is_already_running(self, account_id: str, room_id: str) -> bool:
        return True

    def schedule_full_cycle(self, **_k: Any) -> None:
        return None


def test_pipeline_does_not_block_when_scheduler_returns_none() -> None:
    """scheduler が None を返す時、deferred に積まれる。"""
    pipeline = _StubPipeline()
    scheduler = _StubScheduler(pipeline)
    mgr = MemoryManager(pipeline=pipeline, pipeline_scheduler=scheduler)  # type: ignore[arg-type]

    mgr._trigger_pipeline(turn_count=10, account_id="acc1", room_id="r1")

    assert pipeline.call_count == 0
    assert ("acc1", "r1") in scheduler._deferred
    assert scheduler.schedule_calls == [("acc1", "r1")]


def test_pipeline_drains_deferred_when_scheduler_can_run() -> None:
    """deferred に積まれた scope は次回の run_if_needed で drain される。"""
    pipeline = _StubPipeline()
    scheduler = _StubScheduler(pipeline)
    mgr = MemoryManager(pipeline=pipeline, pipeline_scheduler=scheduler)  # type: ignore[arg-type]

    mgr._trigger_pipeline(turn_count=10, account_id="acc1", room_id="r1")
    assert ("acc1", "r1") in scheduler._deferred

    scheduler._running.add(("acc1", "r1"))
    mgr._trigger_pipeline(turn_count=10, account_id="acc2", room_id="r2")


def test_pipeline_does_nothing_if_already_running() -> None:
    pipeline = _StubPipeline()
    scheduler = _AlwaysRunningScheduler()
    mgr = MemoryManager(pipeline=pipeline, pipeline_scheduler=scheduler)  # type: ignore[arg-type]

    mgr._trigger_pipeline(turn_count=10, account_id="acc1", room_id="r1")

    assert pipeline.call_count == 0


def test_pipeline_skips_if_below_min_turns() -> None:
    pipeline = _StubPipeline()
    scheduler = _StubScheduler(pipeline)
    mgr = MemoryManager(pipeline=pipeline, pipeline_scheduler=scheduler)  # type: ignore[arg-type]

    mgr._trigger_pipeline(turn_count=0, account_id="acc1", room_id="r1")

    assert pipeline.call_count == 0
    assert scheduler._deferred == set()
    assert scheduler.schedule_calls == []
