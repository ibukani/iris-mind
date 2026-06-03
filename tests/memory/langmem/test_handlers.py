"""RelationshipPromotionHandler / AppraisalPromotionHandler のテスト。"""

from __future__ import annotations

from pathlib import Path

import pytest

from iris.limbic.relationship import RelationshipManager
from iris.limbic.stores.appraisal_store import AppraisalEpisodeStore
from iris.limbic.stores.relationship_store import RelationshipStateStore
from iris.memory.langmem.handlers import (
    AppraisalPromotionHandler,
    RelationshipPromotionHandler,
)
from iris.memory.langmem.models import MemoryCandidate

pytestmark = pytest.mark.legacy
# ── RelationshipPromotionHandler ──


def _rel_candidate(**overrides: object) -> MemoryCandidate:
    payload: dict[str, object] = {
        "signal": "trust_increase",
        "evidence": "信頼の発言",
        "suggested_delta": 0.03,
        "field": "trust",
        "confidence": 0.85,
    }
    if "payload" in overrides:
        extra = overrides.pop("payload")
        if isinstance(extra, dict):
            payload.update(extra)
    defaults: dict[str, object] = {
        "target_store": "relationship",
        "payload": payload,
        "confidence": 0.85,
        "source_record_ids": ["r1"],
    }
    defaults.update(overrides)
    return MemoryCandidate(**defaults)  # type: ignore[arg-type]


def test_relationship_handler_applies_positive_delta(tmp_path: Path) -> None:
    manager = RelationshipManager()
    snapshot = RelationshipStateStore(str(tmp_path / "rs.jsonl"))
    handler = RelationshipPromotionHandler(
        relationship_manager=manager,
        snapshot_store=snapshot,
    )
    before = manager.get_state(account_id="acc1").trust
    candidate = _rel_candidate()
    candidate.source_record_ids = ["rec1", "rec2"]
    memory_id = handler.apply(candidate, account_id="acc1", room_id="room1")
    assert memory_id is not None
    after = manager.get_state(account_id="acc1").trust
    assert after > before
    # スナップショットが記録されている
    snaps = snapshot.list_all()
    assert len(snaps) == 1
    assert snaps[0].account_id == "acc1"
    assert snaps[0].source_record_ids == ["rec1", "rec2"]
    assert snaps[0].all_source_record_ids == ["rec1", "rec2"]


def test_relationship_handler_clamps_to_max_delta() -> None:
    manager = RelationshipManager()
    handler = RelationshipPromotionHandler(relationship_manager=manager)
    candidate = _rel_candidate(payload={"suggested_delta": 0.5, "confidence": 0.85})  # 超過
    before = manager.get_state().trust
    handler.apply(candidate)
    after = manager.get_state().trust
    # 単候補の上限 (0.05) * confidence (0.85) = 0.0425 を超えない
    assert after - before <= 0.05 * 0.85 + 1e-9


def test_relationship_handler_negative_clamped_more_strict() -> None:
    """負方向は正方向の 50% の cap までしか下げない。"""
    manager = RelationshipManager()
    handler = RelationshipPromotionHandler(relationship_manager=manager)
    # 最初に大きな positive delta で trust を上げておく
    pos = _rel_candidate(payload={"suggested_delta": 0.04, "confidence": 1.0})
    handler.apply(pos)
    raised = manager.get_state().trust
    # その後 大きな negative delta
    neg = _rel_candidate(
        payload={"suggested_delta": -0.5, "confidence": 1.0, "field": "trust", "signal": "trust_decrease"},
    )
    handler.apply(neg)
    final = manager.get_state().trust
    # 負方向は 0.05 * 0.5 * 1.0 = 0.025 までしか下げない
    assert raised - final <= 0.05 * 0.5 + 1e-9


def test_relationship_handler_low_confidence_skipped() -> None:
    manager = RelationshipManager()
    handler = RelationshipPromotionHandler(relationship_manager=manager)
    candidate = _rel_candidate(confidence=0.4)  # 0.6 未満
    before = manager.get_state().trust
    memory_id = handler.apply(candidate)
    assert memory_id is None
    after = manager.get_state().trust
    assert after == before


def test_relationship_handler_zero_delta_returns_none() -> None:
    manager = RelationshipManager()
    handler = RelationshipPromotionHandler(relationship_manager=manager)
    candidate = _rel_candidate(payload={"suggested_delta": 0.0})
    assert handler.apply(candidate) is None


def test_relationship_handler_familiarity_field() -> None:
    manager = RelationshipManager()
    handler = RelationshipPromotionHandler(relationship_manager=manager)
    candidate = _rel_candidate(
        payload={"suggested_delta": 0.02, "field": "familiarity", "confidence": 0.9},
    )
    before = manager.get_state().familiarity
    handler.apply(candidate)
    after = manager.get_state().familiarity
    assert after > before


# ── AppraisalPromotionHandler ──


def _appraisal_candidate(**overrides: object) -> MemoryCandidate:
    payload: dict[str, object] = {
        "trigger_summary": "嬉しいニュース",
        "appraisal_dimension": "pleasantness",
        "estimated_delta": 0.3,
        "reason": "良かった",
        "confidence": 0.8,
    }
    if "payload" in overrides:
        extra = overrides.pop("payload")
        if isinstance(extra, dict):
            payload.update(extra)
    defaults: dict[str, object] = {
        "target_store": "appraisal",
        "payload": payload,
        "confidence": 0.8,
        "source_record_ids": ["r1"],
    }
    defaults.update(overrides)
    return MemoryCandidate(**defaults)  # type: ignore[arg-type]


def test_appraisal_handler_records_episode(tmp_path: Path) -> None:
    store = AppraisalEpisodeStore(str(tmp_path / "ae.jsonl"))
    handler = AppraisalPromotionHandler(episode_store=store)
    candidate = _appraisal_candidate()
    memory_id = handler.apply(candidate, account_id="acc1", room_id="r1")
    assert memory_id is not None
    episodes = store.list_all()
    assert len(episodes) == 1
    ep = episodes[0]
    assert ep.account_id == "acc1"
    assert ep.appraisal["dimension"] == "pleasantness"
    assert ep.appraisal["source"] == "langmem_candidate"


def test_appraisal_handler_does_not_clamp_to_zero_when_low_confidence(tmp_path: Path) -> None:
    store = AppraisalEpisodeStore(str(tmp_path / "ae.jsonl"))
    handler = AppraisalPromotionHandler(episode_store=store)
    candidate = _appraisal_candidate(confidence=0.4)  # 0.5 未満で skip
    memory_id = handler.apply(candidate)
    assert memory_id is None
    assert store.list_all() == []


def test_appraisal_handler_clamps_extreme_delta(tmp_path: Path) -> None:
    store = AppraisalEpisodeStore(str(tmp_path / "ae.jsonl"))
    handler = AppraisalPromotionHandler(episode_store=store)
    candidate = _appraisal_candidate(
        payload={"estimated_delta": 5.0, "confidence": 1.0, "trigger_summary": "x"},
    )
    handler.apply(candidate)
    ep = store.list_all()[0]
    assert abs(ep.appraisal["estimated_delta_clamped"]) <= handler.max_delta


def test_appraisal_handler_persists_source_record_ids(tmp_path: Path) -> None:
    store = AppraisalEpisodeStore(str(tmp_path / "ae.jsonl"))
    handler = AppraisalPromotionHandler(episode_store=store)
    candidate = _appraisal_candidate()
    candidate.source_record_ids = ["r1", "r2", "r3"]
    handler.apply(candidate, account_id="acc1", room_id="r1")
    ep = store.list_all()[0]
    assert ep.appraisal["source_record_ids"] == ["r1", "r2", "r3"]


# ── PromotionPolicy 経由の統合確認 ──


def test_promotion_policy_routes_relationship_to_handler() -> None:
    from iris.memory.langmem.promotion import PromotionPolicy

    manager = RelationshipManager()
    handler = RelationshipPromotionHandler(relationship_manager=manager)

    # ダミー long_term は PromotionPolicy のコンストラクタ引数
    class _Stub:
        def store_semantic(self, *_a: object, **_k: object) -> None: ...
        def store_episodic(self, *_a: object, **_k: object) -> None: ...

    policy = PromotionPolicy(
        long_term=_Stub(),
        min_confidence=0.5,
        handlers={  # type: ignore[arg-type]
            "relationship": handler,
        },
    )
    before = manager.get_state().trust
    status, _ = policy.promote(_rel_candidate())
    assert status == "promoted"
    assert manager.get_state().trust > before


def test_promotion_policy_routes_appraisal_to_handler(tmp_path: Path) -> None:
    from iris.memory.langmem.promotion import PromotionPolicy

    store = AppraisalEpisodeStore(str(tmp_path / "ae.jsonl"))
    handler = AppraisalPromotionHandler(episode_store=store)

    class _Stub:
        def store_semantic(self, *_a: object, **_k: object) -> None: ...
        def store_episodic(self, *_a: object, **_k: object) -> None: ...

    policy = PromotionPolicy(
        long_term=_Stub(),
        min_confidence=0.5,
        handlers={  # type: ignore[arg-type]
            "appraisal": handler,
        },
    )
    status, _ = policy.promote(_appraisal_candidate())
    assert status == "promoted"
    assert len(store.list_all()) == 1


def test_promotion_policy_rejects_relationship_with_missing_field() -> None:
    """suggested_delta が無い候補は needs_review。"""
    from iris.memory.langmem.promotion import PromotionPolicy

    class _Stub:
        def store_semantic(self, *_a: object, **_k: object) -> None: ...
        def store_episodic(self, *_a: object, **_k: object) -> None: ...

    policy = PromotionPolicy(long_term=_Stub(), min_confidence=0.5)
    candidate = MemoryCandidate(
        target_store="relationship",
        confidence=0.9,
        source_record_ids=["r1"],
        payload={"signal": "trust_increase", "evidence": "発言"},
    )
    status, reason = policy.promote(candidate)
    assert status == "needs_review"
    assert "suggested_delta" in reason
