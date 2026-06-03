"""MemoryCandidateStore / PromotionPolicy の重複検出に関するテスト。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from iris.memory.langmem.models import MemoryCandidate
from iris.memory.langmem.stores import MemoryCandidateStore

pytestmark = pytest.mark.legacy


def _semantic_candidate(**overrides: Any) -> MemoryCandidate:
    payload = {
        "category": "technical",
        "content": "ユーザーは Rust を好む",
        "evidence": "「Rust がいい」",
        "confidence": 0.85,
        "scope": "account",
    }
    payload.update(overrides.pop("payload", {}) or {})
    defaults: dict[str, Any] = {
        "target_store": "semantic",
        "payload": payload,
        "confidence": payload["confidence"],
        "source_record_ids": ["rec1"],
    }
    defaults.update(overrides)
    return MemoryCandidate(**defaults)


def test_candidate_store_blocks_pending_duplicate(tmp_path: Path) -> None:
    store = MemoryCandidateStore(str(tmp_path / "c.jsonl"))
    a = _semantic_candidate()
    b = _semantic_candidate()  # same payload, same scope
    assert store.add(a) is a
    store.add(b)
    # 同じ payload_hash の pending が既に存在するためスキップ
    assert store.count() == 1


def test_candidate_store_allows_after_rejected(tmp_path: Path) -> None:
    store = MemoryCandidateStore(str(tmp_path / "c.jsonl"))
    a = _semantic_candidate()
    store.add(a)
    store.update(a.id, status="rejected", rejection_reason="x")
    b = _semantic_candidate()
    store.add(b)
    assert store.count() == 2


def test_candidate_store_different_account_not_duplicate(tmp_path: Path) -> None:
    store = MemoryCandidateStore(str(tmp_path / "c.jsonl"))
    a = _semantic_candidate(scope_account_id="acc1")
    b = _semantic_candidate(scope_account_id="acc2")
    store.add(a)
    store.add(b)
    assert store.count() == 2


def test_candidate_store_different_target_store_not_duplicate(tmp_path: Path) -> None:
    store = MemoryCandidateStore(str(tmp_path / "c.jsonl"))
    a = _semantic_candidate(target_store="semantic")
    b = _semantic_candidate(target_store="style")
    store.add(a)
    store.add(b)
    assert store.count() == 2


def test_candidate_store_explicit_duplicate_allow(tmp_path: Path) -> None:
    store = MemoryCandidateStore(str(tmp_path / "c.jsonl"), allow_duplicates=True)
    a = _semantic_candidate()
    b = _semantic_candidate()
    store.add(a)
    store.add(b)
    assert store.count() == 2


def test_candidate_store_find_by_payload_hash(tmp_path: Path) -> None:
    store = MemoryCandidateStore(str(tmp_path / "c.jsonl"))
    a = _semantic_candidate(scope_account_id="acc1", scope_room_id="room1")
    store.add(a)
    found = store.find_by_payload_hash(
        target_store="semantic",
        payload_hash=a.payload_hash,
        account_id="acc1",
        room_id="room1",
    )
    assert found is not None
    assert found.id == a.id
    # スコープ違いでは見つからない
    miss = store.find_by_payload_hash(
        target_store="semantic",
        payload_hash=a.payload_hash,
        account_id="acc2",
        room_id="room1",
    )
    assert miss is None


def test_candidate_store_payload_with_extra_whitespace_collides(tmp_path: Path) -> None:
    """空白差は ``compute_payload_signature`` が trim して吸収するため同じ hash になる。"""
    store = MemoryCandidateStore(str(tmp_path / "c.jsonl"))
    a = _semantic_candidate()
    a.payload["content"] = "ユーザーは Rust を好む"
    store.add(a)
    b = _semantic_candidate()
    b.payload["content"] = "  ユーザーは Rust を好む  "
    store.add(b)
    # 同じ hash とみなされ、pending 重複として 1 件だけになる
    assert store.count() == 1
    assert a.payload_hash == b.payload_hash
