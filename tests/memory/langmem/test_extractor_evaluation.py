"""LangMem extractor の評価ハーネス。

Fake chat model を使い、実運用で期待される挙動のスナップショットを保証する。
ケース:
- 明示的好み → semantic candidate が生成される
- 一度きりジョーク → スタイル candidate なし
- 嫌悪発言 → avoidance (高 confidence)
- センシティブ → rejected (PromotionPolicy で)
- relationship の delta はクランプ対象
- 日本語はそのまま保持
- 空会話 → 候補なし
- 弱い根拠 → low confidence
- persona_patch は confidence>=0.9 のみ昇格、それ以外は needs_review
- persona_patch は自動適用しない (PersonaPatchPolicy 側で承認)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from iris.memory.archive.models import ConversationRecord
from iris.memory.consolidation.log_store import MemoryConsolidationLogStore
from iris.memory.langmem.extractor import LangMemExtractor, make_job_scope_resolver
from iris.memory.langmem.handlers import PersonaPatchPromotionHandler
from iris.memory.langmem.models import MemoryCandidate, MemoryExtractionJob
from iris.memory.langmem.promotion import PromotionPolicy
from iris.memory.langmem.stores import MemoryCandidateStore
from iris.memory.procedural.persona_patch_store import (
    PersonaPatchCandidateStore,
    PersonaPatchPolicy,
)
from tests.fakes.llm import FakeChatModelForLangMem, make_fake_thread_extractor


class _FakeLongTerm:
    def __init__(self) -> None:
        self.semantic: list[dict[str, Any]] = []
        self.episodic: list[dict[str, Any]] = []

    def store_semantic(self, data: Any, room_id: str = "", account_id: str = "") -> None:
        self.semantic.append({"data": data, "room_id": room_id, "account_id": account_id})

    def store_episodic(self, data: Any, kind: str = "", room_id: str = "", account_id: str = "") -> None:
        self.episodic.append({"data": data, "kind": kind, "room_id": room_id, "account_id": account_id})


def _make_extractor(
    tmp_path: Path,
    response: Any,
    *,
    account_id: str = "acc1",
    room_id: str = "room1",
) -> tuple[LangMemExtractor, FakeChatModelForLangMem, MemoryCandidateStore]:
    chat = FakeChatModelForLangMem()
    chat.set_responses([response])
    candidate_store = MemoryCandidateStore(str(tmp_path / "c.jsonl"))
    extractor = LangMemExtractor(
        chat_model=chat,
        candidate_store=candidate_store,
        thread_extractor_factory=make_fake_thread_extractor,
        scope_resolver=make_job_scope_resolver(account_id, room_id),
    )
    return extractor, chat, candidate_store


def test_explicit_preference_produces_semantic_candidate(tmp_path: Path) -> None:
    extractor, _chat, _store = _make_extractor(
        tmp_path,
        {
            "items": [
                {
                    "category": "technical",
                    "content": "ユーザーは Rust を好む",
                    "evidence": "「Rust がいい」",
                    "confidence": 0.9,
                    "scope": "account",
                }
            ]
        },
    )
    job = MemoryExtractionJob(pass_type="semantic", account_id="acc1", room_id="room1")
    candidates = extractor.run(
        job,
        [ConversationRecord(role="user", content="Rust がいい")],
    )
    assert len(candidates) == 1
    c = candidates[0]
    assert c.target_store == "semantic"
    assert c.payload["content"] == "ユーザーは Rust を好む"
    assert c.confidence == 0.9
    assert c.scope_account_id == "acc1"
    assert c.scope_room_id == "room1"
    assert len(c.payload_hash) == 64


def test_one_time_joke_yields_no_style_candidate(tmp_path: Path) -> None:
    extractor, _chat, _store = _make_extractor(
        tmp_path,
        {"items": []},  # 1 度きりジョークは stable ではないため無視
    )
    job = MemoryExtractionJob(pass_type="style")
    candidates = extractor.run(
        job,
        [ConversationRecord(role="user", content="たまには寿司でも食べるか")],
    )
    assert candidates == []


def test_dislike_yields_avoidance_high_confidence(tmp_path: Path) -> None:
    extractor, _chat, _store = _make_extractor(
        tmp_path,
        {
            "items": [
                {
                    "category": "avoidance",
                    "content": "ユーザーは長い会議を嫌う",
                    "evidence": "「長いのダメ」",
                    "confidence": 0.9,
                    "scope": "account",
                }
            ]
        },
    )
    job = MemoryExtractionJob(pass_type="semantic")
    candidates = extractor.run(
        job,
        [ConversationRecord(role="user", content="長いのダメ")],
    )
    assert len(candidates) == 1
    assert candidates[0].payload["category"] == "avoidance"
    assert candidates[0].confidence >= 0.85


def test_sensitive_keyword_rejected_at_promotion(tmp_path: Path) -> None:
    """store には入るが PromotionPolicy の sensitive guard で rejected される。"""
    long_term = _FakeLongTerm()
    log = MemoryConsolidationLogStore(str(tmp_path / "log.jsonl"))
    policy = PromotionPolicy(long_term=long_term, consolidation_log=log, min_confidence=0.5)
    candidate = MemoryCandidate(
        target_store="semantic",
        confidence=0.8,
        source_record_ids=["r1"],
        payload={
            "category": "personal_preference",
            "content": "ユーザーの住所は東京",
            "evidence": "明言",
            "confidence": 0.8,
        },
    )
    status, reason = policy.promote(candidate, room_id="room1", account_id="acc1")
    assert status == "rejected"
    assert "sensitive" in reason
    assert long_term.semantic == []


def test_relationship_suggested_delta_is_bounded(tmp_path: Path) -> None:
    extractor, _chat, _store = _make_extractor(
        tmp_path,
        {
            "items": [
                {
                    "signal": "trust_increase",
                    "evidence": "信頼を寄せる発言",
                    "suggested_delta": 0.08,
                    "confidence": 0.85,
                }
            ]
        },
    )
    job = MemoryExtractionJob(pass_type="relationship")
    candidates = extractor.run(
        job,
        [ConversationRecord(role="user", content="ありがとう")],
    )
    assert len(candidates) == 1
    assert abs(candidates[0].payload["suggested_delta"]) <= 0.1


def test_japanese_evidence_preserved_through_pipeline(tmp_path: Path) -> None:
    extractor, _chat, _store = _make_extractor(
        tmp_path,
        {
            "items": [
                {
                    "category": "personal_preference",
                    "content": "アイスを好む",
                    "evidence": "「アイス好き」と発言",
                    "confidence": 0.9,
                    "scope": "account",
                }
            ]
        },
    )
    long_term = _FakeLongTerm()
    log = MemoryConsolidationLogStore(str(tmp_path / "log.jsonl"))
    policy = PromotionPolicy(long_term=long_term, consolidation_log=log, min_confidence=0.5)
    job = MemoryExtractionJob(
        pass_type="semantic",
        account_id="acc1",
        room_id="room1",
        source_record_ids=["r1"],
    )
    candidates = extractor.run(
        job,
        [ConversationRecord(role="user", content="アイス好き")],
    )
    record = policy.evaluate(candidates, room_id="room1", account_id="acc1")
    assert len(record.created_memory_ids) == 1
    assert long_term.semantic[0]["data"]["content"] == "アイスを好む"
    assert long_term.semantic[0]["data"]["evidence"] == "「アイス好き」と発言"


def test_empty_conversation_yields_no_candidates(tmp_path: Path) -> None:
    extractor, _chat, _store = _make_extractor(tmp_path, {"items": []})
    candidates = extractor.run(
        MemoryExtractionJob(pass_type="semantic"),
        [],
    )
    assert candidates == []


def test_weak_evidence_means_low_confidence(tmp_path: Path) -> None:
    extractor, _chat, _store = _make_extractor(
        tmp_path,
        {
            "items": [
                {
                    "category": "personal_preference",
                    "content": "もしかしたら Rust を好むかも",
                    "evidence": "発言から推察",
                    "confidence": 0.4,
                    "scope": "account",
                }
            ]
        },
    )
    candidates = extractor.run(
        MemoryExtractionJob(pass_type="semantic"),
        [ConversationRecord(role="user", content="たぶん Rust いいかも")],
    )
    assert len(candidates) == 1
    assert candidates[0].confidence < 0.5
    # promotion では low_confidence で rejected される
    long_term = _FakeLongTerm()
    policy = PromotionPolicy(long_term=long_term, min_confidence=0.75)
    status, reason = policy.promote(candidates[0])
    assert status == "rejected"
    assert "low_confidence" in reason


def test_persona_patch_high_confidence_goes_to_review_not_auto_applied(tmp_path: Path) -> None:
    """persona_patch は confidence が 0.9 を超えても自動適用せず承認待ち。"""
    persona_store = PersonaPatchCandidateStore(str(tmp_path / "pp.jsonl"))
    persona_policy = PersonaPatchPolicy(persona_store)
    long_term = _FakeLongTerm()
    log = MemoryConsolidationLogStore(str(tmp_path / "log.jsonl"))
    policy = PromotionPolicy(
        long_term=long_term,
        consolidation_log=log,
        min_confidence=0.5,
        handlers={  # type: ignore[arg-type]
            "persona_patch": PersonaPatchPromotionHandler(
                store=persona_store,
                policy=persona_policy,
            ),
        },
    )
    candidate = MemoryCandidate(
        target_store="persona_patch",
        confidence=0.95,
        source_record_ids=["r1"],
        payload={
            "target_file": ".iris/config/iris_profile.md",
            "proposed_patch": "- ユーザーには敬語を使わずタメ口で接する。",
            "reason": "ユーザーはタメ口を希望",
            "evidence": "「タメ口で話して」",
        },
    )
    status, _ = policy.promote(candidate, room_id="r1", account_id="acc1")
    assert status == "promoted"
    # 適用は承認フローでのみ実行
    assert all(p.status == "pending" for p in persona_store.list_all())
    # 適用前のファイルは変更されていない
    profile = tmp_path / "iris_profile.md"
    if profile.exists():
        assert "タメ口" not in profile.read_text(encoding="utf-8")


def test_persona_patch_low_confidence_becomes_needs_review(tmp_path: Path) -> None:
    persona_store = PersonaPatchCandidateStore(str(tmp_path / "pp.jsonl"))
    long_term = _FakeLongTerm()
    log = MemoryConsolidationLogStore(str(tmp_path / "log.jsonl"))
    policy = PromotionPolicy(
        long_term=long_term,
        consolidation_log=log,
        min_confidence=0.5,
        handlers={  # type: ignore[arg-type]
            "persona_patch": PersonaPatchPromotionHandler(
                store=persona_store,
                policy=PersonaPatchPolicy(persona_store),
            ),
        },
    )
    candidate = MemoryCandidate(
        target_store="persona_patch",
        confidence=0.7,
        source_record_ids=["r1"],
        payload={
            "target_file": ".iris/config/iris_profile.md",
            "proposed_patch": "- もっと饒舌にする",
            "reason": "静かな傾向",
            "evidence": "",
        },
    )
    status, reason = policy.promote(candidate)
    assert status == "needs_review"
    assert "low_confidence" in reason
    # needs_review の low_confidence エントリが保存される
    pending = persona_store.list_pending()
    assert len(pending) == 1
    assert pending[0].metadata.get("low_confidence") is True


def test_style_kind_assigned_in_extractor_output(tmp_path: Path) -> None:
    extractor, _chat, _store = _make_extractor(
        tmp_path,
        {
            "items": [
                {
                    "kind": "successful_pattern",
                    "content": "テスト駆動開発の手順",
                    "evidence": "TDD を好む発言",
                    "confidence": 0.85,
                    "activation_condition": "新機能実装時",
                }
            ]
        },
    )
    job = MemoryExtractionJob(pass_type="style")
    candidates = extractor.run(
        job,
        [ConversationRecord(role="user", content="TDD でやろう")],
    )
    assert len(candidates) == 1
    assert candidates[0].target_store == "style"
    assert candidates[0].payload["kind"] == "successful_pattern"


@pytest.mark.parametrize(
    ("pass_type", "expected_target"),
    [
        ("semantic", "semantic"),
        ("episodic", "episodic"),
        ("style", "style"),
        ("relationship", "relationship"),
        ("appraisal", "appraisal"),
        ("persona_patch", "persona_patch"),
    ],
)
def test_all_passes_route_to_correct_target_store(tmp_path: Path, pass_type: str, expected_target: str) -> None:
    extractor, _chat, _store = _make_extractor(
        tmp_path,
        {"items": [_make_minimal_item(pass_type)]},
    )
    candidates = extractor.run(
        MemoryExtractionJob(pass_type=pass_type),  # type: ignore[arg-type]
        [ConversationRecord(role="user", content="x")],
    )
    assert len(candidates) == 1
    assert candidates[0].target_store == expected_target


def _make_minimal_item(pass_type: str) -> dict[str, Any]:
    if pass_type == "semantic":
        return {
            "category": "personal_preference",
            "content": "テスト用好み",
            "evidence": "発言",
            "confidence": 0.8,
            "scope": "account",
        }
    if pass_type == "episodic":
        return {
            "situation": "実装",
            "user_intent": "質問",
            "assistant_action": "回答",
            "result": "成功",
            "lesson": "短く答える",
            "confidence": 0.8,
        }
    if pass_type == "style":
        return {
            "kind": "successful_pattern",
            "content": "テスト用スタイル",
            "evidence": "発言",
            "confidence": 0.8,
            "activation_condition": "実装前",
        }
    if pass_type == "relationship":
        return {
            "signal": "trust_increase",
            "evidence": "発言",
            "suggested_delta": 0.02,
            "confidence": 0.8,
        }
    if pass_type == "appraisal":
        return {
            "trigger_summary": "嬉しいニュース",
            "appraisal_dimension": "pleasantness",
            "estimated_delta": 0.4,
            "reason": "良かった",
            "confidence": 0.8,
        }
    if pass_type == "persona_patch":
        return {
            "target_file": ".iris/config/iris_profile.md",
            "proposed_patch": "- テスト用 patch",
            "reason": "テスト",
            "evidence": "発言",
            "confidence": 0.95,
        }
    raise AssertionError(f"unknown pass_type={pass_type}")
