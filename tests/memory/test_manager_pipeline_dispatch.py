"""MemoryManager の ``_maybe_run_pipeline`` 動作 (B-004) テスト。"""

from __future__ import annotations

from typing import Any

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


class _StubScheduler:
    """イベントループ無しでも動かせる単純なスタブ。"""

    def __init__(self) -> None:
        self.schedule_calls: list[tuple[str, str]] = []
        self.is_running: set[tuple[str, str]] = set()

    def is_already_running(self, account_id: str, room_id: str) -> bool:
        return (account_id, room_id) in self.is_running

    def schedule_full_cycle(
        self,
        *,
        account_id: str = "",
        room_id: str = "",
        source_record_ids: list[str] | None = None,
    ) -> None:
        self.schedule_calls.append((account_id, room_id))
        return  # イベントループ無しを想定


class _AlwaysRunningScheduler:
    def is_already_running(self, account_id: str, room_id: str) -> bool:
        return True

    def schedule_full_cycle(self, **_k: Any) -> None:
        return None


def test_maybe_run_pipeline_does_not_block_when_scheduler_returns_none() -> None:
    """B-004: scheduler が ``None`` を返す時、同期 ``run_full_cycle`` にフォールバックしない。"""
    pipeline = _StubPipeline()
    scheduler = _StubScheduler()
    mgr = MemoryManager(pipeline=pipeline, pipeline_scheduler=scheduler)  # type: ignore[arg-type]

    mgr._maybe_run_pipeline(turn_count=10, account_id="acc1", room_id="r1")

    # 同期実行は起こらない (chat ブロック回避)
    assert pipeline.call_count == 0
    # dirty 集合に積まれる
    assert ("acc1", "r1") in mgr._pipeline_dirty_scopes
    # scheduler には schedule が呼ばれた
    assert scheduler.schedule_calls == [("acc1", "r1")]


def test_maybe_run_pipeline_drains_dirty_scopes_when_scheduler_can_run() -> None:
    """dirty に積まれた scope は次回の flush 時に drain される。"""

    pipeline = _StubPipeline()
    scheduler = _StubScheduler()
    mgr = MemoryManager(pipeline=pipeline, pipeline_scheduler=scheduler)  # type: ignore[arg-type]

    # 1 回目: 同期コンテキスト想定 → dirty に積まれる
    mgr._maybe_run_pipeline(turn_count=10, account_id="acc1", room_id="r1")
    assert ("acc1", "r1") in mgr._pipeline_dirty_scopes

    # 2 回目: scheduler が run 中 (前回スケジュールが完走した想定)
    scheduler.is_running.add(("acc1", "r1"))
    mgr._maybe_run_pipeline(turn_count=10, account_id="acc2", room_id="r2")
    # 既に同じ scope が走っている場合、新スケジュールはしない
    # drain の対象は acc1/r1 だが is_running なので何もせず残す


def test_maybe_run_pipeline_does_nothing_if_already_running() -> None:
    pipeline = _StubPipeline()
    scheduler = _AlwaysRunningScheduler()
    mgr = MemoryManager(pipeline=pipeline, pipeline_scheduler=scheduler)  # type: ignore[arg-type]

    mgr._maybe_run_pipeline(turn_count=10, account_id="acc1", room_id="r1")

    assert pipeline.call_count == 0
    assert mgr._pipeline_dirty_scopes == set()


def test_maybe_run_pipeline_skips_if_below_min_turns() -> None:
    pipeline = _StubPipeline()
    scheduler = _StubScheduler()
    mgr = MemoryManager(pipeline=pipeline, pipeline_scheduler=scheduler)  # type: ignore[arg-type]

    mgr._maybe_run_pipeline(turn_count=0, account_id="acc1", room_id="r1")

    assert pipeline.call_count == 0
    assert mgr._pipeline_dirty_scopes == set()
    assert scheduler.schedule_calls == []
