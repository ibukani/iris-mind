"""Limbic persistent stores のテスト。"""

from __future__ import annotations

from pathlib import Path

from iris.limbic.models import (
    AppraisalDimensions,
    CompanionEmotion,
    EmotionResult,
    Mood,
    PlutchikEmotion,
    RelationshipState,
)
from iris.limbic.stores.appraisal_store import AppraisalEpisode, AppraisalEpisodeStore
from iris.limbic.stores.relationship_store import RelationshipStateStore


def _make_emotion_result(relationship: RelationshipState) -> EmotionResult:
    return EmotionResult(
        appraisal=AppraisalDimensions(),
        emotion=CompanionEmotion(primary=PlutchikEmotion.JOY, intensity=0.4),
        mood=Mood(valence=0.1, arousal=0.1, dominance=0.0),
        relationship=relationship,
    )


def test_relationship_state_store_roundtrip(tmp_path: Path) -> None:
    store = RelationshipStateStore(str(tmp_path / "r.jsonl"))
    state = RelationshipState(trust=0.4, familiarity=0.2, interaction_count=3)
    snap = store.save_snapshot("acc1", state)
    assert snap.account_id == "acc1"
    assert snap.state.trust == 0.4

    loaded = store.load_for_account("acc1")
    assert loaded is not None
    assert loaded.state.familiarity == 0.2


def test_relationship_state_store_overwrites(tmp_path: Path) -> None:
    store = RelationshipStateStore(str(tmp_path / "r.jsonl"))
    s1 = RelationshipState(trust=0.1)
    s2 = RelationshipState(trust=0.5)
    store.save_snapshot("acc1", s1)
    store.save_snapshot("acc1", s2)
    loaded = store.load_for_account("acc1")
    assert loaded is not None
    assert loaded.state.trust == 0.5
    assert len(store.list_for_account("acc1")) == 1


def test_relationship_state_store_separate_accounts(tmp_path: Path) -> None:
    store = RelationshipStateStore(str(tmp_path / "r.jsonl"))
    store.save_snapshot("acc1", RelationshipState(trust=0.1))
    store.save_snapshot("acc2", RelationshipState(trust=0.9))
    acc1 = store.load_for_account("acc1")
    acc2 = store.load_for_account("acc2")
    assert acc1 is not None
    assert acc2 is not None
    assert acc1.state.trust == 0.1
    assert acc2.state.trust == 0.9


def test_relationship_state_store_persists_source_record_ids(tmp_path: Path) -> None:
    store = RelationshipStateStore(str(tmp_path / "r.jsonl"))
    state = RelationshipState(trust=0.5, familiarity=0.3, interaction_count=2)
    store.save_snapshot("acc1", state, source_record_ids=["r1", "r2"])
    snap = store.load_for_account("acc1")
    assert snap is not None
    assert snap.source_record_ids == ["r1", "r2"]
    assert snap.all_source_record_ids == ["r1", "r2"]


def test_relationship_state_store_merges_source_record_ids(tmp_path: Path) -> None:
    store = RelationshipStateStore(str(tmp_path / "r.jsonl"))
    store.save_snapshot("acc1", RelationshipState(trust=0.3), source_record_ids=["r1", "r2"])
    store.save_snapshot("acc1", RelationshipState(trust=0.5), source_record_ids=["r3"])
    snap = store.load_for_account("acc1")
    assert snap is not None
    # 直近スナップは最新 source_record_ids
    assert snap.source_record_ids == ["r3"]
    # 累計はマージされ重複除去
    assert snap.all_source_record_ids == ["r1", "r2", "r3"]


def test_appraisal_episode_store_from_result(tmp_path: Path) -> None:
    store = AppraisalEpisodeStore(str(tmp_path / "a.jsonl"))
    relationship = RelationshipState(trust=0.6, familiarity=0.4, interaction_count=5)
    result = _make_emotion_result(relationship)
    ep = AppraisalEpisode.from_result(
        result,
        account_id="acc1",
        room_id="r1",
        input_record_id="rec1",
        trigger_summary="嬉しい報告",
    )
    store.add(ep)
    items = store.list_for_account("acc1")
    assert len(items) == 1
    assert items[0].trigger_summary == "嬉しい報告"
    assert items[0].relationship_after.trust == 0.6
    assert "primary" in items[0].emotion
