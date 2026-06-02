"""Raw Conversation Archive Store のテスト。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from iris.memory.archive.models import ConversationRecord
from iris.memory.archive.policy import ArchivePolicy
from iris.memory.archive.store import RawConversationArchiveStore


def _make_store(tmp_path: Path, **overrides: int) -> RawConversationArchiveStore:
    int_overrides: dict[str, int] = {k: int(v) for k, v in overrides.items()}
    policy = ArchivePolicy(archive_dir=str(tmp_path / "archive"))
    for k, v in int_overrides.items():
        setattr(policy, k, v)
    return RawConversationArchiveStore(policy=policy)


def test_append_creates_file(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    rec_id = store.append(ConversationRecord(role="user", content="hi", room_id="r1"))
    assert rec_id is not None
    files = list((tmp_path / "archive").glob("*.jsonl"))
    assert len(files) == 1
    line = files[0].read_text(encoding="utf-8").strip()
    payload = json.loads(line)
    assert payload["role"] == "user"
    assert payload["content"] == "hi"
    assert payload["id"] == rec_id


def test_append_multiple_records(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    for idx in range(5):
        store.append(ConversationRecord(role="user", content=f"msg {idx}"))
    rows = store.load_all()
    assert len(rows) == 5
    assert [r["content"] for r in rows] == [f"msg {i}" for i in range(5)]


def test_rollover_when_file_exceeds_size(tmp_path: Path) -> None:
    store = _make_store(tmp_path, max_per_file_bytes=200)
    for _ in range(20):
        store.append(ConversationRecord(content="x" * 50))
    files = sorted((tmp_path / "archive").glob("*.jsonl"))
    assert len(files) > 1
    rows = store.load_all()
    assert len(rows) == 20


def test_query_by_time(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    rec1 = ConversationRecord(content="older", timestamp="2025-01-01T00:00:00+00:00")
    rec2 = ConversationRecord(content="newer", timestamp="2025-12-31T23:59:59+00:00")
    store.append(rec1)
    store.append(rec2)
    rows = store.query_by_time("2025-06-01T00:00:00+00:00")
    assert len(rows) == 1
    assert rows[0]["content"] == "newer"


def test_find_by_id(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    rec = ConversationRecord(content="findme")
    rec_id = store.append(rec)
    found = store.find_by_id(rec_id)  # type: ignore[arg-type]
    assert found is not None
    assert found["content"] == "findme"
    assert store.find_by_id("does-not-exist") is None


def test_append_with_dict_payload(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    rid = store.append({"role": "user", "content": "hi from dict", "room_id": "r2"})
    assert rid is not None
    rows = store.load_all()
    assert rows[-1]["content"] == "hi from dict"
    assert rows[-1]["id"] == rid


def test_disabled_policy_silently_skips(tmp_path: Path) -> None:
    policy = ArchivePolicy(archive_dir=str(tmp_path / "archive"), enabled=False)
    store = RawConversationArchiveStore(policy=policy)
    rec_id = store.append(ConversationRecord(content="x"))
    assert rec_id is None
    assert not (tmp_path / "archive").exists()


def test_load_all_handles_corrupt_line(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    store.append(ConversationRecord(content="ok"))
    archive_dir = tmp_path / "archive"
    file = next(archive_dir.glob("*.jsonl"))
    with file.open("a", encoding="utf-8") as f:
        f.write("not-valid-json-line\n")
    store.append(ConversationRecord(content="ok2"))
    rows = store.load_all()
    assert len(rows) == 2
    assert {r["content"] for r in rows} == {"ok", "ok2"}


def test_append_failure_does_not_raise(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """書き込み失敗時もメインフローを壊さないこと。"""
    store = _make_store(tmp_path)

    def _raise(*_a: object, **_k: object) -> object:
        raise OSError("disk full")

    from iris.memory.archive import store as store_mod

    monkeypatch.setattr(store_mod.Path, "open", _raise)  # type: ignore[attr-defined]
    rec_id = store.append(ConversationRecord(content="will-fail"))
    assert rec_id is None  # 失敗しても None 返却で例外を伝播しない


def test_evict_old_files(tmp_path: Path) -> None:
    """ファイル数が ``keep_recent_files`` を超えると古いファイルから削除される。"""
    store = _make_store(tmp_path, keep_recent_files=2, max_per_file_bytes=50)
    for _ in range(20):
        store.append(ConversationRecord(content="x"))
    files = sorted((tmp_path / "archive").glob("*.jsonl"))
    assert len(files) == 2
