"""PersonaPatchCandidateStore / PersonaPatchPolicy のテスト。"""

from __future__ import annotations

from pathlib import Path

from iris.memory.procedural.persona_patch_models import PersonaPatchCandidate
from iris.memory.procedural.persona_patch_store import (
    PersonaPatchCandidateStore,
    PersonaPatchPolicy,
)


def test_persona_patch_store_list_pending(tmp_path: Path) -> None:
    store = PersonaPatchCandidateStore(str(tmp_path / "p.jsonl"))
    store.add(PersonaPatchCandidate(reason="tone", proposed_patch="new text"))
    store.add(
        PersonaPatchCandidate(
            reason="tone2",
            proposed_patch="new text2",
            status="approved",
        )
    )
    pending = store.list_pending()
    assert len(pending) == 1
    assert pending[0].reason == "tone"


def test_approve_and_reject(tmp_path: Path) -> None:
    store = PersonaPatchCandidateStore(str(tmp_path / "p.jsonl"))
    c = store.add(PersonaPatchCandidate(reason="x", proposed_patch="y"))
    approved = store.approve(c.id)
    assert approved is not None
    assert approved.status == "approved"
    rejected = store.reject(c.id, reason="too aggressive")
    assert rejected is not None
    assert rejected.status == "rejected"


def test_apply_approved_writes_file_and_creates_backup(tmp_path: Path) -> None:
    target = tmp_path / "iris_profile.md"
    target.write_text("old content", encoding="utf-8")
    store = PersonaPatchCandidateStore(str(tmp_path / "p.jsonl"))
    c = store.add(
        PersonaPatchCandidate(
            reason="update",
            proposed_patch="new content",
            target_file=str(target),
        )
    )
    store.approve(c.id)
    policy = PersonaPatchPolicy(store)
    ok = policy.apply_approved(c.id)
    assert ok is True
    assert target.read_text(encoding="utf-8") == "new content"
    backup = target.with_suffix(target.suffix + ".bak")
    assert backup.read_text(encoding="utf-8") == "old content"
    persisted = store.find(c.id)
    assert persisted is not None
    assert persisted.status == "applied"


def test_apply_rejected_does_nothing(tmp_path: Path) -> None:
    target = tmp_path / "iris_profile.md"
    target.write_text("old", encoding="utf-8")
    store = PersonaPatchCandidateStore(str(tmp_path / "p.jsonl"))
    c = store.add(
        PersonaPatchCandidate(
            reason="update",
            proposed_patch="new",
            target_file=str(target),
        )
    )
    policy = PersonaPatchPolicy(store)
    ok = policy.apply_approved(c.id)
    assert ok is False
    assert target.read_text(encoding="utf-8") == "old"
