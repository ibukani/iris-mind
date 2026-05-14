from __future__ import annotations

import os
import tempfile

from iris.memory.stores import AgentsMdStore, EpisodicStore, SemanticStore


def test_agents_md_store_load_missing() -> None:
    store = AgentsMdStore(path=os.path.join(tempfile.gettempdir(), "nonexistent_profile.md"))
    assert store.load() == ""


def test_agents_md_store_write_and_read() -> None:
    fd, path = tempfile.mkstemp(suffix=".md")
    os.close(fd)
    store = AgentsMdStore(path=path, max_bytes=2048)
    store.update("# Iris Profile\nHello")
    assert store.load() == "# Iris Profile\nHello"
    os.unlink(path)


def test_agents_md_store_truncate_by_lines() -> None:
    fd, path = tempfile.mkstemp(suffix=".md")
    os.close(fd)
    store = AgentsMdStore(path=path, max_bytes=20)
    # Truncation removes entire lines from the end
    content = "line1\nline2\nline3\nline4"
    store.update(content)
    loaded = store.load()
    assert len(loaded.encode("utf-8")) <= 20
    os.unlink(path)


def test_episodic_store_add_and_get() -> None:
    fd, path = tempfile.mkstemp(suffix=".jsonl")
    os.close(fd)
    store = EpisodicStore(path=path, max_entries=30)
    store.add("hello world")
    recent = store.get_recent(1)
    assert recent == ["hello world"]
    os.unlink(path)


def test_episodic_store_max_entries() -> None:
    fd, path = tempfile.mkstemp(suffix=".jsonl")
    os.close(fd)
    store = EpisodicStore(path=path, max_entries=3)
    for i in range(5):
        store.add(f"entry {i}")
    recent = store.get_recent(10)
    assert len(recent) == 3
    assert recent[-1] == "entry 4"
    os.unlink(path)


def test_episodic_store_clear() -> None:
    fd, path = tempfile.mkstemp(suffix=".jsonl")
    os.close(fd)
    store = EpisodicStore(path=path, max_entries=30)
    store.add("test")
    store.clear()
    assert store.get_recent(1) == []
    assert not os.path.exists(path)


def test_episodic_store_empty() -> None:
    store = EpisodicStore(path=os.path.join(tempfile.gettempdir(), "nonexistent.jsonl"))
    assert store.get_recent(5) == []


def test_semantic_store_add_and_search() -> None:
    tmpdir = tempfile.mkdtemp()
    try:
        path = os.path.join(tmpdir, "semantic.jsonl")
        store = SemanticStore(path=path, max_entries=100, vector_db_path=os.path.join(tmpdir, "chroma"))
        store.add({"content": "Iris は Python で書かれている", "tags": ["tech"]})
        store.add({"content": "ユーザーはコーディングが好き", "tags": ["preference"]})
        results = store.search("Python", max_results=5)
        assert len(results) >= 1
    finally:
        import shutil

        shutil.rmtree(tmpdir, ignore_errors=True)


def test_semantic_store_duplicate_prevention() -> None:
    tmpdir = tempfile.mkdtemp()
    try:
        path = os.path.join(tmpdir, "semantic.jsonl")
        store = SemanticStore(path=path, max_entries=100, vector_db_path=os.path.join(tmpdir, "chroma"))
        store.add({"content": "duplicate content", "tags": []})
        store.add({"content": "duplicate content", "tags": []})
        entries = store._load_all()
        assert len(entries) == 1
    finally:
        import shutil

        shutil.rmtree(tmpdir, ignore_errors=True)


def test_semantic_store_clear() -> None:
    tmpdir = tempfile.mkdtemp()
    try:
        path = os.path.join(tmpdir, "semantic.jsonl")
        store = SemanticStore(path=path, max_entries=100, vector_db_path=os.path.join(tmpdir, "chroma"))
        store.add({"content": "test", "tags": []})
        store.clear()
        assert store._load_all() == []
    finally:
        import shutil

        shutil.rmtree(tmpdir, ignore_errors=True)


def test_semantic_store_persistence() -> None:
    tmpdir = tempfile.mkdtemp()
    try:
        path = os.path.join(tmpdir, "semantic.jsonl")
        store1 = SemanticStore(path=path, max_entries=100, vector_db_path=os.path.join(tmpdir, "chroma"))
        store1.add({"content": "persisted data", "tags": ["test"]})
        del store1
        store2 = SemanticStore(path=path, max_entries=100, vector_db_path=os.path.join(tmpdir, "chroma"))
        entries = store2._load_all()
        assert len(entries) == 1
        assert entries[0]["content"] == "persisted data"
    finally:
        import shutil

        shutil.rmtree(tmpdir, ignore_errors=True)


def test_semantic_store_adds_default_fields() -> None:
    tmpdir = tempfile.mkdtemp()
    try:
        path = os.path.join(tmpdir, "semantic.jsonl")
        store = SemanticStore(path=path, max_entries=100, vector_db_path=os.path.join(tmpdir, "chroma"))
        store.add({"content": "test"})
        entries = store._load_all()
        assert entries[0]["id"] is not None
        assert entries[0]["timestamp"] is not None
        assert entries[0]["tags"] is not None
    finally:
        import shutil

        shutil.rmtree(tmpdir, ignore_errors=True)
