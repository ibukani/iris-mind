"""MemoryExtractionJobStore / MemoryCandidateStore のテスト。"""

from __future__ import annotations

from pathlib import Path

from iris.memory.langmem.models import (
    MemoryCandidate,
    MemoryExtractionJob,
)
from iris.memory.langmem.stores import (
    MemoryCandidateStore,
    MemoryExtractionJobStore,
)


def test_job_store_add_and_update(tmp_path: Path) -> None:
    store = MemoryExtractionJobStore(str(tmp_path / "jobs.jsonl"))
    job = MemoryExtractionJob(pass_type="semantic", source_record_ids=["a", "b"])
    store.add(job)
    loaded = store.find(job.id)
    assert loaded is not None
    assert loaded.status == "pending"

    updated = store.update(job.id, status="running")
    assert updated is not None
    assert updated.status == "running"
    assert updated.updated_at != job.updated_at or updated.id == job.id


def test_job_store_list_filtered(tmp_path: Path) -> None:
    store = MemoryExtractionJobStore(str(tmp_path / "jobs.jsonl"))
    store.add(MemoryExtractionJob(pass_type="semantic", status="pending"))
    store.add(MemoryExtractionJob(pass_type="episodic", status="pending"))
    store.add(MemoryExtractionJob(pass_type="semantic", status="failed"))

    pending = store.list_filtered(status="pending")
    assert len(pending) == 2
    semantic_pending = store.list_filtered(status="pending", pass_type="semantic")
    assert len(semantic_pending) == 1
    assert store.count(status="failed") == 1


def test_candidate_store_pending_filter(tmp_path: Path) -> None:
    store = MemoryCandidateStore(str(tmp_path / "candidates.jsonl"))
    c1 = MemoryCandidate(target_store="semantic", confidence=0.9)
    c2 = MemoryCandidate(target_store="semantic", confidence=0.3, status="rejected")
    c3 = MemoryCandidate(target_store="style", confidence=0.8)
    store.add(c1)
    store.add(c2)
    store.add(c3)

    pending = store.list_filtered(status="pending")
    assert len(pending) == 2
    assert {c.id for c in pending} == {c1.id, c3.id}

    promoted = store.update(c1.id, status="promoted")
    assert promoted is not None
    assert promoted.status == "promoted"
    assert store.count(status="promoted") == 1


def test_candidate_store_persists_across_instances(tmp_path: Path) -> None:
    path = str(tmp_path / "candidates.jsonl")
    s1 = MemoryCandidateStore(path)
    s1.add(MemoryCandidate(payload={"k": "v"}, confidence=0.5))
    s2 = MemoryCandidateStore(path)
    items = s2.list_all()
    assert len(items) == 1
    assert items[0].payload == {"k": "v"}
