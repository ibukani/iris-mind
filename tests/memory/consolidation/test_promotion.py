"""PromotionPolicy / MemoryConsolidationLogStore のテスト。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from iris.memory.consolidation.log_store import MemoryConsolidationLogStore
from iris.memory.langmem.models import MemoryCandidate
from iris.memory.langmem.promotion import PromotionPolicy


class _FakeLongTerm:
    def __init__(self) -> None:
        self.semantic: list[dict[str, Any]] = []
        self.episodic: list[dict[str, Any]] = []

    def store_semantic(self, data: Any, room_id: str = "", account_id: str = "") -> None:
        self.semantic.append({"data": data, "room_id": room_id, "account_id": account_id})

    def store_episodic(self, data: Any, kind: str = "", room_id: str = "", account_id: str = "") -> None:
        self.episodic.append({"data": data, "kind": kind, "room_id": room_id, "account_id": account_id})


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


def test_promote_strong_semantic_candidate(tmp_path: Path) -> None:
    long_term = _FakeLongTerm()
    log = MemoryConsolidationLogStore(str(tmp_path / "log.jsonl"))
    policy = PromotionPolicy(long_term=long_term, consolidation_log=log, min_confidence=0.75)

    status, _ = policy.promote(_semantic_candidate())
    assert status == "promoted"
    assert len(long_term.semantic) == 1
    assert long_term.semantic[0]["data"]["content"] == "ユーザーは Rust を好む"


def test_reject_low_confidence(tmp_path: Path) -> None:
    long_term = _FakeLongTerm()
    policy = PromotionPolicy(long_term=long_term, min_confidence=0.75)
    status, reason = policy.promote(_semantic_candidate(confidence=0.5))
    assert status == "rejected"
    assert "low_confidence" in reason
    assert long_term.semantic == []


def test_reject_empty_content(tmp_path: Path) -> None:
    long_term = _FakeLongTerm()
    policy = PromotionPolicy(long_term=long_term)
    c = _semantic_candidate(payload={"content": "", "evidence": "x", "confidence": 0.9})
    status, reason = policy.promote(c)
    assert status == "rejected"
    assert "empty_content" in reason


def test_reject_sensitive_keyword(tmp_path: Path) -> None:
    long_term = _FakeLongTerm()
    policy = PromotionPolicy(long_term=long_term)
    c = _semantic_candidate(payload={"content": "ユーザーの住所は東京", "evidence": "明言", "confidence": 0.85})
    status, reason = policy.promote(c)
    assert status == "rejected"
    assert "sensitive" in reason


def test_reject_missing_source_records(tmp_path: Path) -> None:
    long_term = _FakeLongTerm()
    policy = PromotionPolicy(long_term=long_term)
    c = _semantic_candidate(source_record_ids=[])
    status, reason = policy.promote(c)
    assert status == "needs_review"
    assert "no_source" in reason


def test_evaluate_writes_consolidation_log(tmp_path: Path) -> None:
    long_term = _FakeLongTerm()
    log = MemoryConsolidationLogStore(str(tmp_path / "log.jsonl"))
    policy = PromotionPolicy(long_term=long_term, consolidation_log=log)

    candidates = [
        _semantic_candidate(),
        _semantic_candidate(confidence=0.2, payload={"content": "weak", "evidence": "x"}),
    ]
    record = policy.evaluate(candidates, account_id="acc1")
    assert len(record.created_memory_ids) == 1
    assert len(record.rejected_candidate_ids) == 1
    persisted = log.list_all()
    assert len(persisted) == 1
    assert persisted[0].created_memory_ids == record.created_memory_ids


def test_avoidance_category_requires_higher_confidence(tmp_path: Path) -> None:
    long_term = _FakeLongTerm()
    policy = PromotionPolicy(long_term=long_term)
    c = _semantic_candidate(
        payload={
            "category": "avoidance",
            "content": "ユーザーは長い会議を嫌う",
            "evidence": "「長いのダメ」",
            "confidence": 0.78,
        }
    )
    status, reason = policy.promote(c)
    assert status == "rejected"
    assert "avoidance" in reason
