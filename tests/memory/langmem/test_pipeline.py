"""MemoryPipeline の単体テスト。

統合テストは ``tests/memory/langmem/test_scheduler.py::test_real_pipeline_scheduler_integration``
に任せており、ここでは ``run_full_cycle`` の 6 パス網羅 (B-002) と
``scope_resolver`` 注入 (B-009) をピンポイントで検証する。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from iris.kernel.config import LangMemConfig, MemoryConfig
from iris.memory.archive.policy import ArchivePolicy
from iris.memory.archive.store import RawConversationArchiveStore
from iris.memory.consolidation.log_store import MemoryConsolidationLogStore
from iris.memory.langmem.extractor import LangMemExtractor
from iris.memory.langmem.pipeline import MemoryPipeline
from iris.memory.langmem.promotion import PromotionPolicy
from iris.memory.langmem.schemas import (
    AppraisalExtractionResult,
    EpisodicExtractionResult,
    PersonaPatchExtractionResult,
    RelationshipExtractionResult,
    SemanticExtractionResult,
    StyleExtractionResult,
)
from iris.memory.langmem.stores import MemoryCandidateStore, MemoryExtractionJobStore
from tests.fakes.llm import FakeChatModelForLangMem, make_fake_thread_extractor

pytestmark = pytest.mark.legacy


def _build_pipeline(tmp_path: Path) -> tuple[MemoryPipeline, FakeChatModelForLangMem, list[str]]:
    """テスト用パイプラインを構築する。``FakeChatModel`` を返す。"""
    archive = RawConversationArchiveStore(policy=ArchivePolicy(archive_dir=str(tmp_path / "arc")))
    chat = FakeChatModelForLangMem(name="test")
    candidate_store = MemoryCandidateStore(str(tmp_path / "c.jsonl"))
    job_store = MemoryExtractionJobStore(str(tmp_path / "j.jsonl"))
    log = MemoryConsolidationLogStore(str(tmp_path / "log.jsonl"))
    extractor = LangMemExtractor(
        chat_model=chat,
        candidate_store=candidate_store,
        thread_extractor_factory=make_fake_thread_extractor,
    )

    class _Stub:
        def store_semantic(self, *_a: object, **_k: object) -> None: ...
        def store_episodic(self, *_a: object, **_k: object) -> None: ...

    promotion = PromotionPolicy(long_term=_Stub(), consolidation_log=log)
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
    return (
        pipeline,
        chat,
        [
            SemanticExtractionResult.__name__,
            EpisodicExtractionResult.__name__,
            StyleExtractionResult.__name__,
            RelationshipExtractionResult.__name__,
            AppraisalExtractionResult.__name__,
            PersonaPatchExtractionResult.__name__,
        ],
    )


def test_run_full_cycle_includes_persona_patch(tmp_path: Path) -> None:
    """``run_full_cycle`` が 6 パス (semantic/episodic/style/relationship/appraisal/persona_patch) を順に実行する。"""
    pipeline, _chat, _expected = _build_pipeline(tmp_path)
    archive = pipeline._archive
    archive.append({"id": "r1", "role": "user", "content": "こんにちは", "direction": "inbound"})
    archive.append({"id": "r2", "role": "assistant", "content": "やあ", "direction": "outbound"})

    result = pipeline.run_full_cycle(account_id="acc1", room_id="r1")

    # 6 パスすべてが結果 dict に存在し、リストが返る
    assert set(result.keys()) == {
        "semantic",
        "episodic",
        "style",
        "relationship",
        "appraisal",
        "persona_patch",
    }
    for items in result.values():
        assert items == []


def test_run_pass_uses_per_job_scope_resolver(tmp_path: Path) -> None:
    """``run_pass`` が ``make_job_scope_resolver(account_id, room_id)`` を resolver として注入する。"""
    pipeline, chat, _expected = _build_pipeline(tmp_path)
    archive = pipeline._archive
    archive.append({"id": "r1", "role": "user", "content": "user text", "direction": "inbound"})

    chat.set_responses(
        [
            {
                "items": [
                    {
                        "category": "personal_preference",
                        "content": "甘いもの好き",
                        "evidence": "user said so",
                        "confidence": 0.9,
                    }
                ]
            },
        ]
    )
    candidates = pipeline.run_pass("semantic", account_id="acc1", room_id="room1")
    assert len(candidates) == 1
    c = candidates[0]
    # デフォルト resolver ではなく Job のスコープが反映されている
    assert c.scope_account_id == "acc1"
    assert c.scope_room_id == "room1"
    assert c.payload_hash
