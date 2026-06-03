"""LangMem Extractor のテスト (フェイク ChatModel 使用)。"""

from __future__ import annotations

from pathlib import Path

import pytest

from iris.memory.archive.models import ConversationRecord
from iris.memory.langmem.extractor import LangMemExtractor
from iris.memory.langmem.models import MemoryExtractionJob
from iris.memory.langmem.stores import MemoryCandidateStore
from tests.fakes.llm import FakeChatModelForLangMem, make_fake_thread_extractor

pytestmark = pytest.mark.legacy


def _make_extractor(
    tmp_path: Path, response: object
) -> tuple[LangMemExtractor, FakeChatModelForLangMem, MemoryCandidateStore]:
    chat = FakeChatModelForLangMem()
    chat.set_responses([response])
    candidate_store = MemoryCandidateStore(str(tmp_path / "c.jsonl"))
    extractor = LangMemExtractor(
        chat_model=chat,
        candidate_store=candidate_store,
        thread_extractor_factory=make_fake_thread_extractor,
    )
    return extractor, chat, candidate_store


def test_extractor_creates_candidates(tmp_path: Path) -> None:
    extractor, _chat, store = _make_extractor(
        tmp_path,
        {
            "items": [
                {
                    "category": "technical",
                    "content": "ユーザーは Rust を好む",
                    "evidence": "「Rust がいい」と言及",
                    "confidence": 0.85,
                    "scope": "account",
                }
            ]
        },
    )
    job = MemoryExtractionJob(pass_type="semantic", source_record_ids=["r1"])
    candidates = extractor.run(
        job,
        [ConversationRecord(role="user", content="Rust がいい")],
    )
    assert len(candidates) == 1
    assert candidates[0].target_store == "semantic"
    assert candidates[0].payload["content"] == "ユーザーは Rust を好む"
    assert candidates[0].confidence == 0.85
    assert len(store.list_all()) == 1


def test_extractor_empty_result_is_safe(tmp_path: Path) -> None:
    extractor, _chat, store = _make_extractor(tmp_path, {"items": []})
    job = MemoryExtractionJob(pass_type="semantic")
    candidates = extractor.run(
        job,
        [ConversationRecord(role="user", content="こんにちは")],
    )
    assert candidates == []
    assert store.list_all() == []


def test_extractor_handles_no_records(tmp_path: Path) -> None:
    extractor, _chat, _store = _make_extractor(tmp_path, {"items": []})
    job = MemoryExtractionJob(pass_type="semantic")
    candidates = extractor.run(job, [])
    assert candidates == []


def test_extractor_failure_marks_no_candidates(tmp_path: Path) -> None:
    """ファクトリが例外を投げるパスは graceful に空リストを返す。"""
    candidate_store = MemoryCandidateStore(str(tmp_path / "c.jsonl"))

    def _bad_factory(_m: object, _s: object, _i: object) -> object:
        raise RuntimeError("langmem not installed")

    extractor = LangMemExtractor(
        chat_model=FakeChatModelForLangMem(),
        candidate_store=candidate_store,
        thread_extractor_factory=_bad_factory,
    )
    job = MemoryExtractionJob(pass_type="style")
    candidates = extractor.run(
        job,
        [ConversationRecord(role="user", content="x")],
    )
    assert candidates == []


def test_extractor_routes_pass_to_target_store(tmp_path: Path) -> None:
    extractor, _chat, _store = _make_extractor(
        tmp_path,
        {
            "items": [
                {
                    "kind": "successful_pattern",
                    "content": "テスト駆動の具体手順",
                    "evidence": "ユーザーが unit test 追加を依頼",
                    "confidence": 0.8,
                    "activation_condition": "実装前",
                }
            ]
        },
    )
    job = MemoryExtractionJob(pass_type="style")
    candidates = extractor.run(
        job,
        [ConversationRecord(role="user", content="test 追加して")],
    )
    assert len(candidates) == 1
    assert candidates[0].target_store == "style"


def test_extractor_does_not_call_llm_when_records_empty(tmp_path: Path) -> None:
    chat = FakeChatModelForLangMem()
    chat.set_responses([{"items": []}])
    extractor = LangMemExtractor(
        chat_model=chat,
        candidate_store=MemoryCandidateStore(str(tmp_path / "c.jsonl")),
        thread_extractor_factory=make_fake_thread_extractor,
    )
    candidates = extractor.run(MemoryExtractionJob(pass_type="semantic"), [])
    assert candidates == []
    assert chat.call_count == 0
