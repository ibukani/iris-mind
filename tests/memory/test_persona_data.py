from __future__ import annotations

import os
from pathlib import Path
import tempfile

from iris.memory.persona_data import _MAX_ENTRIES, PersonaData


def _make_data() -> PersonaData:
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    os.unlink(path)
    return PersonaData(path=path)


def _clean(path: str | Path) -> None:
    p = Path(path)
    if p.exists():
        os.unlink(str(p))


def test_add_and_get_top() -> None:
    data = _make_data()
    # 新フィールド名 speech_quirks で追加
    data.add_entry("speech_quirks", "丁寧な話し方")
    data.add_entry("speech_quirks", "親しみやすい口調")
    data.add_entry("state_traits", "好奇心旺盛")
    top = data.get_top("speech_quirks", 1)
    assert len(top) == 1
    _clean(data.path)


def test_new_field_names() -> None:
    """新フィールド名（speech_quirks / state_traits）でデータが保存・取得できること。"""
    data = _make_data()
    data.add_entry("speech_quirks", "丁寧な話し方")
    data.add_entry("state_traits", "好奇心旺盛")
    assert len(data.get_all("speech_quirks")) == 1
    assert len(data.get_all("state_traits")) == 1
    _clean(data.path)


def test_get_top_limit() -> None:
    data = _make_data()
    for i in range(10):
        data.add_entry("speech_quirks", f"style {i}")
    assert len(data.get_top("speech_quirks", 3)) == 3
    _clean(data.path)


def test_get_all() -> None:
    data = _make_data()
    data.add_entry("speech_quirks", "a")
    data.add_entry("speech_quirks", "b")
    data.add_entry("state_traits", "c")
    all_cat = data.get_all("speech_quirks")
    assert len(all_cat) == 2
    assert all_cat[0]["text"] == "a"
    _clean(data.path)


def test_clear() -> None:
    data = _make_data()
    data.add_entry("speech_quirks", "content")
    data.clear()
    assert data.get_all("speech_quirks") == []
    _clean(data.path)


def test_empty_category() -> None:
    data = _make_data()
    assert data.get_top("nonexistent") == []
    assert data.get_all("nonexistent") == []
    _clean(data.path)


def test_max_entries_limit() -> None:
    """_MAX_ENTRIES を超えると古いエントリが削除されること。"""
    data = _make_data()

    # _MAX_ENTRIES 件埋める（各 count=2 にする）
    for i in range(_MAX_ENTRIES):
        data.add_entry("speech_quirks", f"style{i}")
        data.add_entry("speech_quirks", f"style{i}")  # count: 2

    # 1件追加すると count=1 の新エントリは削られる
    data.add_entry("speech_quirks", "newcomer")

    all_entries = data.get_all("speech_quirks")
    assert len(all_entries) == _MAX_ENTRIES
    texts = [e["text"] for e in all_entries]
    assert "newcomer" not in texts

    _clean(data.path)
