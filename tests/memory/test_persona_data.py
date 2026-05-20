from __future__ import annotations

import os
from pathlib import Path
import tempfile

from iris.memory.personality.persona_data import PersonaData


def _make_data(max_entries: int = 100) -> PersonaData:
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    os.unlink(path)
    return PersonaData(path=path, max_entries=max_entries)


def _clean(path: str | Path) -> None:
    p = Path(path)
    if p.exists():
        os.unlink(str(p))


def test_add_and_get_top() -> None:
    data = _make_data()
    data.add_entry("speech_style", "丁寧な話し方")
    data.add_entry("speech_style", "親しみやすい口調")
    data.add_entry("personality_traits", "好奇心旺盛")
    top = data.get_top("speech_style", 1)
    assert len(top) == 1
    assert top[0]["text"] == "丁寧な話し方"
    _clean(data.path)


def test_get_top_limit() -> None:
    data = _make_data()
    for i in range(10):
        data.add_entry("speech_style", f"style {i}")
    assert len(data.get_top("speech_style", 3)) == 3
    _clean(data.path)


def test_get_all() -> None:
    data = _make_data()
    data.add_entry("speech_style", "a")
    data.add_entry("speech_style", "b")
    data.add_entry("personality_traits", "c")
    all_cat = data.get_all("speech_style")
    assert len(all_cat) == 2
    assert all_cat[0]["text"] == "a"
    _clean(data.path)


def test_clear() -> None:
    data = _make_data()
    data.add_entry("speech_style", "content")
    data.clear()
    assert data.get_all("speech_style") == []
    _clean(data.path)


def test_empty_category() -> None:
    data = _make_data()
    assert data.get_top("nonexistent") == []
    assert data.get_all("nonexistent") == []
    _clean(data.path)


def test_max_entries_limit() -> None:
    data = _make_data(max_entries=2)

    # 頻度をバラけさせて追加
    data.add_entry("speech_style", "style1")
    data.add_entry("speech_style", "style1")  # count: 2

    data.add_entry("speech_style", "style2")
    data.add_entry("speech_style", "style2")  # count: 2

    # 現在 max_entries=2 なので、style1, style2 で満杯
    # 3件目(style3, count=1)を追加すると、頻度の低い style3 が即座に削られる
    data.add_entry("speech_style", "style3")  # count: 1 になるが削られる

    all_entries = data.get_all("speech_style")
    assert len(all_entries) == 2
    texts = [e["text"] for e in all_entries]

    assert "style1" in texts
    assert "style2" in texts
    assert "style3" not in texts

    _clean(data.path)
