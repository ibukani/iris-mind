"""PersonaPatchCandidateStore / PersonaPatchPolicy のテスト。"""

from __future__ import annotations

from pathlib import Path

from iris.memory.procedural.persona_patch_models import PersonaPatchCandidate
from iris.memory.procedural.persona_patch_store import (
    PersonaPatchCandidateStore,
    PersonaPatchPolicy,
)


def _profile_path(tmp_path: Path) -> str:
    return str(tmp_path / ".iris" / "config" / "iris_profile.md")


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


def test_apply_approved_appends_by_default(tmp_path: Path) -> None:
    target = tmp_path / ".iris" / "config" / "iris_profile.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("# original\n\nfirst section\n", encoding="utf-8")
    store = PersonaPatchCandidateStore(str(tmp_path / "p.jsonl"))
    c = store.add(
        PersonaPatchCandidate(
            reason="update",
            proposed_patch="appended section",
            target_file=".iris/config/iris_profile.md",
        )
    )
    store.approve(c.id)
    policy = PersonaPatchPolicy(store, base_dir=tmp_path)
    ok = policy.apply_approved(c.id)
    assert ok is True
    contents = target.read_text(encoding="utf-8")
    assert "# original" in contents
    assert "first section" in contents
    assert "appended section" in contents
    backup = target.with_suffix(target.suffix + ".bak")
    assert backup.read_text(encoding="utf-8") == "# original\n\nfirst section\n"
    persisted = store.find(c.id)
    assert persisted is not None
    assert persisted.status == "applied"


def test_apply_approved_replace_rewrites_file(tmp_path: Path) -> None:
    target = tmp_path / ".iris" / "config" / "iris_profile.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("old", encoding="utf-8")
    store = PersonaPatchCandidateStore(str(tmp_path / "p.jsonl"))
    c = store.add(
        PersonaPatchCandidate(
            reason="update",
            proposed_patch="new content",
            target_file=".iris/config/iris_profile.md",
        )
    )
    store.approve(c.id)
    policy = PersonaPatchPolicy(store, base_dir=tmp_path)
    ok = policy.apply_approved(c.id, replace=True)
    assert ok is True
    assert target.read_text(encoding="utf-8") == "new content"
    backup = target.with_suffix(target.suffix + ".bak")
    assert backup.read_text(encoding="utf-8") == "old"


def test_apply_approved_rejects_absolute_path(tmp_path: Path) -> None:
    store = PersonaPatchCandidateStore(str(tmp_path / "p.jsonl"))
    c = store.add(
        PersonaPatchCandidate(
            reason="update",
            proposed_patch="evil",
            target_file="/etc/passwd",
        )
    )
    store.approve(c.id)
    policy = PersonaPatchPolicy(store, base_dir=tmp_path)
    assert policy.apply_approved(c.id) is False
    persisted = store.find(c.id)
    assert persisted is not None
    assert persisted.status == "approved"  # 適用されなかった


def test_apply_approved_rejects_path_outside_profile_dir(tmp_path: Path) -> None:
    store = PersonaPatchCandidateStore(str(tmp_path / "p.jsonl"))
    c = store.add(
        PersonaPatchCandidate(
            reason="update",
            proposed_patch="evil",
            target_file="AGENTS.md",
        )
    )
    store.approve(c.id)
    policy = PersonaPatchPolicy(store, base_dir=tmp_path)
    assert policy.apply_approved(c.id) is False


def test_apply_approved_rejects_path_traversal(tmp_path: Path) -> None:
    store = PersonaPatchCandidateStore(str(tmp_path / "p.jsonl"))
    c = store.add(
        PersonaPatchCandidate(
            reason="update",
            proposed_patch="evil",
            target_file=".iris/config/../AGENTS.md",
        )
    )
    store.approve(c.id)
    policy = PersonaPatchPolicy(store, base_dir=tmp_path)
    assert policy.apply_approved(c.id) is False


def test_apply_approved_rejects_non_md_file(tmp_path: Path) -> None:
    store = PersonaPatchCandidateStore(str(tmp_path / "p.jsonl"))
    c = store.add(
        PersonaPatchCandidate(
            reason="update",
            proposed_patch="evil",
            target_file=".iris/config/settings.json",
        )
    )
    store.approve(c.id)
    policy = PersonaPatchPolicy(store, base_dir=tmp_path)
    assert policy.apply_approved(c.id) is False


def test_apply_rejected_does_nothing(tmp_path: Path) -> None:
    target = tmp_path / ".iris" / "config" / "iris_profile.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("old", encoding="utf-8")
    store = PersonaPatchCandidateStore(str(tmp_path / "p.jsonl"))
    c = store.add(
        PersonaPatchCandidate(
            reason="update",
            proposed_patch="new",
            target_file=".iris/config/iris_profile.md",
        )
    )
    policy = PersonaPatchPolicy(store, base_dir=tmp_path)
    ok = policy.apply_approved(c.id)
    assert ok is False
    assert target.read_text(encoding="utf-8") == "old"
