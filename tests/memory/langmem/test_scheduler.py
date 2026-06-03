"""MemoryPipelineScheduler のテスト。"""

from __future__ import annotations

import asyncio
from pathlib import Path
import threading
import time
from typing import Any

from iris.kernel.config import LangMemConfig, MemoryConfig
from iris.memory.archive.policy import ArchivePolicy
from iris.memory.archive.store import RawConversationArchiveStore
from iris.memory.consolidation.log_store import MemoryConsolidationLogStore
from iris.memory.langmem.pipeline import MemoryPipeline
from iris.memory.langmem.scheduler import MemoryPipelineScheduler
from iris.memory.langmem.stores import MemoryCandidateStore, MemoryExtractionJobStore


class _StubChatModel:
    name = "stub"

    def __init__(self) -> None:
        self.call_count = 0
        self.last_messages: list[Any] = []
        self.responses: list[Any] = []
        self.response_index = 0

    def set_responses(self, responses: list[Any]) -> None:
        self.responses = list(responses)
        self.response_index = 0

    def get_next_response(self) -> Any:
        if not self.responses:
            return None
        resp = self.responses[self.response_index % len(self.responses)]
        self.response_index += 1
        return resp

    def record(self, messages: list[Any]) -> None:
        self.call_count += 1
        self.last_messages = list(messages)


class _DummyPipeline:
    """本物の ``MemoryPipeline`` の代わりに ``run_full_cycle`` の呼び出しを観測する。"""

    def __init__(self, *, slow: bool = False) -> None:
        self.enabled = True
        self.calls: list[dict[str, Any]] = []
        self.slow = slow
        self._lock = threading.Lock()

    def run_full_cycle(self, **kwargs: Any) -> dict[str, list[Any]]:
        with self._lock:
            self.calls.append(kwargs)
        if self.slow:
            time.sleep(0.1)
        return {"semantic": [], "episodic": [], "style": [], "relationship": [], "appraisal": []}

    def run_pass(self, *args: Any, **kwargs: Any) -> list[Any]:
        with self._lock:
            self.calls.append({"pass": args, **kwargs})
        return []


def test_scheduler_returns_none_when_no_event_loop() -> None:
    pipeline = _DummyPipeline()
    scheduler = MemoryPipelineScheduler(pipeline)  # type: ignore[arg-type]
    # 同期コンテキスト (イベントループ無し) では schedule は None を返す
    result = scheduler.schedule_full_cycle(account_id="a", room_id="r")
    assert result is None
    # フォールバックで同期 run は直接呼ばれる
    pipeline.run_full_cycle(account_id="a", room_id="r")
    assert len(pipeline.calls) == 1


def test_scheduler_dedupes_concurrent_calls() -> None:
    """同一 (account_id, room_id) で重複スケジュールした場合 1 つしか実行しない。"""
    pipeline = _DummyPipeline(slow=True)
    scheduler = MemoryPipelineScheduler(pipeline)  # type: ignore[arg-type]

    async def _main() -> None:
        t1 = scheduler.schedule_full_cycle(account_id="acc1", room_id="room1")
        t2 = scheduler.schedule_full_cycle(account_id="acc1", room_id="room1")
        assert t1 is not None
        assert t2 is None  # 重複抑制
        await t1
        assert len(pipeline.calls) == 1

    asyncio.run(_main())


def test_scheduler_different_scope_runs_independently() -> None:
    pipeline = _DummyPipeline(slow=True)
    scheduler = MemoryPipelineScheduler(pipeline)  # type: ignore[arg-type]

    async def _main() -> None:
        t1 = scheduler.schedule_full_cycle(account_id="acc1", room_id="room1")
        t2 = scheduler.schedule_full_cycle(account_id="acc2", room_id="room1")
        t3 = scheduler.schedule_full_cycle(account_id="acc1", room_id="room2")
        assert t1 is not None
        assert t2 is not None
        assert t3 is not None
        await asyncio.gather(t1, t2, t3)
        assert len(pipeline.calls) == 3

    asyncio.run(_main())


def test_scheduler_runs_in_background_thread() -> None:
    """``asyncio.to_thread`` 経由で呼ばれるためメインループをブロックしない。"""
    pipeline = _DummyPipeline(slow=True)
    scheduler = MemoryPipelineScheduler(pipeline)  # type: ignore[arg-type]

    async def _main() -> None:
        t1 = scheduler.schedule_full_cycle(account_id="acc1", room_id="room1")
        assert t1 is not None
        # メインスレッドを 50ms 以内に戻せる = ブロックしていない
        start = time.time()
        await asyncio.sleep(0.05)
        elapsed = time.time() - start
        assert elapsed < 0.08
        await t1

    asyncio.run(_main())


def test_scheduler_captures_exception() -> None:
    """バックグラウンド実行中の例外は握り潰され、stats に記録される。"""

    class _FailingPipeline(_DummyPipeline):
        def run_full_cycle(self, **kwargs: Any) -> dict[str, list[Any]]:
            raise RuntimeError("boom")

    pipeline = _FailingPipeline()
    scheduler = MemoryPipelineScheduler(pipeline)  # type: ignore[arg-type]

    async def _main() -> None:
        t1 = scheduler.schedule_full_cycle(account_id="acc1", room_id="room1")
        assert t1 is not None
        # 例外でもタスクは完了する (None が戻り値)
        result = await t1
        assert result is None
        stats = scheduler.stats
        assert stats.total_failed >= 1
        assert "boom" in stats.last_error

    asyncio.run(_main())


def test_scheduler_is_already_running() -> None:
    pipeline = _DummyPipeline(slow=True)
    scheduler = MemoryPipelineScheduler(pipeline)  # type: ignore[arg-type]

    async def _main() -> None:
        assert scheduler.is_already_running("acc1", "r1") is False
        t = scheduler.schedule_full_cycle(account_id="acc1", room_id="r1")
        assert scheduler.is_already_running("acc1", "r1") is True
        assert scheduler.is_already_running("acc2", "r1") is False
        assert t is not None
        await t
        # 完了後は False に戻る
        assert scheduler.is_already_running("acc1", "r1") is False

    asyncio.run(_main())


def test_scheduler_shutdown_cancels_pending() -> None:
    pipeline = _DummyPipeline(slow=True)
    scheduler = MemoryPipelineScheduler(pipeline)  # type: ignore[arg-type]

    async def _main() -> None:
        t1 = scheduler.schedule_full_cycle(account_id="acc1", room_id="r1")
        t2 = scheduler.schedule_full_cycle(account_id="acc2", room_id="r2")
        assert t1 is not None
        assert t2 is not None
        await scheduler.shutdown(cancel=True)
        # 完了後は再スケジュールできる
        t3 = scheduler.schedule_full_cycle(account_id="acc1", room_id="r1")
        assert t3 is not None
        await t3

    asyncio.run(_main())


def test_scheduler_does_not_attach_to_unrelated_pipelines() -> None:
    """スタブ Pipeline で scheduler を使えることの本テスト (実 pipeline との分離確認)。"""
    pipeline = _DummyPipeline()
    scheduler = MemoryPipelineScheduler(pipeline)  # type: ignore[arg-type]
    assert scheduler.stats.active_tasks == 0


def test_scheduler_concurrent_thread_safety_on_tasks_dict() -> None:
    """B-006: 複数スレッドから ``is_already_running`` / ``stats`` を叩いても
    競合せず ``RuntimeError`` にならない (``_tasks_lock`` 保護の確認)。
    """
    import threading

    pipeline = _DummyPipeline(slow=True)
    scheduler = MemoryPipelineScheduler(pipeline)  # type: ignore[arg-type]

    async def _main() -> None:
        t = scheduler.schedule_full_cycle(account_id="acc1", room_id="r1")
        assert t is not None
        # 並行スレッドから _tasks を観測しても例外が出なければ OK
        errors: list[Exception] = []

        def _probe() -> None:
            try:
                for _ in range(50):
                    _ = scheduler.is_already_running("acc1", "r1")
                    _ = scheduler.stats
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=_probe) for _ in range(4)]
        for th in threads:
            th.start()
        for th in threads:
            th.join()
        assert errors == []
        await t

    asyncio.run(_main())


# 実 MemoryPipeline との統合 (低速だが本当の wiring 確認)
def test_real_pipeline_scheduler_integration(tmp_path: Path) -> None:
    """実 ``MemoryPipeline`` を使い、scheduler 経由で ``run_full_cycle`` が動くことを確認。"""
    from iris.memory.langmem.extractor import LangMemExtractor
    from iris.memory.langmem.promotion import PromotionPolicy
    from tests.fakes.llm import make_fake_thread_extractor

    archive = RawConversationArchiveStore(policy=ArchivePolicy(archive_dir=str(tmp_path / "arc")))
    chat = _StubChatModel()
    chat.set_responses([{"items": []}])

    candidate_store = MemoryCandidateStore(str(tmp_path / "c.jsonl"))
    job_store = MemoryExtractionJobStore(str(tmp_path / "j.jsonl"))
    log = MemoryConsolidationLogStore(str(tmp_path / "log.jsonl"))

    extractor = LangMemExtractor(
        chat_model=chat,
        candidate_store=candidate_store,
        thread_extractor_factory=make_fake_thread_extractor,
    )
    promotion = PromotionPolicy(long_term=_FakeLongTerm(), consolidation_log=log)  # type: ignore[arg-type]

    mem_cfg = MemoryConfig(
        episodic_path=str(tmp_path / "e.jsonl"),
        semantic_path=str(tmp_path / "s.jsonl"),
        vector_db_path=str(tmp_path / "v"),
        agents_md_path=str(tmp_path / "AGENTS.md"),
        archive_dir=str(tmp_path / "arc2"),
        candidate_path=str(tmp_path / "c2.jsonl"),
        job_path=str(tmp_path / "j2.jsonl"),
        consolidation_log_path=str(tmp_path / "log2.jsonl"),
        style_memory_path=str(tmp_path / "s3.jsonl"),
        persona_patch_path=str(tmp_path / "pp.jsonl"),
        relationship_state_path=str(tmp_path / "rs.jsonl"),
        appraisal_episode_path=str(tmp_path / "ae.jsonl"),
    )
    cfg = LangMemConfig(enabled=True, model_role="memory")

    pipeline = MemoryPipeline(
        config=cfg,
        memory_config=mem_cfg,
        archive=archive,
        job_store=job_store,
        candidate_store=candidate_store,
        extractor=extractor,
        promotion_policy=promotion,
        consolidation_log=log,
    )
    scheduler = MemoryPipelineScheduler(pipeline)

    async def _main() -> None:
        t = scheduler.schedule_full_cycle(account_id="acc1", room_id="r1")
        assert t is not None
        result = await t
        # 空 records では {} が返る
        assert isinstance(result, dict)

    asyncio.run(_main())


class _FakeLongTerm:
    def store_semantic(self, data: Any, room_id: str = "", account_id: str = "") -> None: ...
    def store_episodic(self, data: Any, kind: str = "", room_id: str = "", account_id: str = "") -> None: ...
