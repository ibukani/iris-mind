from __future__ import annotations

from iris.memory.persona_data import _MAX_ENTRIES, PersonaData


def _make_data() -> PersonaData:
    return PersonaData()


def test_add_and_get_top() -> None:
    data = _make_data()
    data.add_entry("speech_quirks", "丁寧な話し方")
    data.add_entry("speech_quirks", "親しみやすい口調")
    data.add_entry("state_traits", "好奇心旺盛")
    top = data.get_top("speech_quirks", 1)
    assert len(top) == 1


def test_new_field_names() -> None:
    data = _make_data()
    data.add_entry("speech_quirks", "丁寧な話し方")
    data.add_entry("state_traits", "好奇心旺盛")
    assert len(data.get_all("speech_quirks")) == 1
    assert len(data.get_all("state_traits")) == 1


def test_get_top_limit() -> None:
    data = _make_data()
    for i in range(10):
        data.add_entry("speech_quirks", f"style {i}")
    assert len(data.get_top("speech_quirks", 3)) == 3


def test_get_all() -> None:
    data = _make_data()
    data.add_entry("speech_quirks", "a")
    data.add_entry("speech_quirks", "b")
    data.add_entry("state_traits", "c")
    all_cat = data.get_all("speech_quirks")
    assert len(all_cat) == 2
    assert all_cat[0]["text"] == "a"


def test_clear() -> None:
    data = _make_data()
    data.add_entry("speech_quirks", "content")
    data.clear()
    assert data.get_all("speech_quirks") == []


def test_empty_category() -> None:
    data = _make_data()
    assert data.get_top("nonexistent") == []
    assert data.get_all("nonexistent") == []


def test_max_entries_limit() -> None:
    data = _make_data()

    for i in range(_MAX_ENTRIES):
        data.add_entry("speech_quirks", f"style{i}")
        data.add_entry("speech_quirks", f"style{i}")

    data.add_entry("speech_quirks", "newcomer")

    all_entries = data.get_all("speech_quirks")
    assert len(all_entries) == _MAX_ENTRIES
    texts = [e["text"] for e in all_entries]
    assert "newcomer" not in texts


def test_interests_add_and_decay() -> None:
    data = _make_data()
    data.add_interest("宇宙の起源", 0.8)
    interests = data.get_interests()
    assert len(interests) == 1
    assert interests[0]["topic"] == "宇宙の起源"
    assert interests[0]["weight"] == 0.8

    data.add_interest("宇宙の起源", 0.1)
    interests = data.get_interests()
    assert interests[0]["weight"] == 0.9

    data.add_interest("量子力学", 0.5)
    interests = data.get_interests()
    assert len(interests) == 2
    assert interests[0]["topic"] == "宇宙の起源"
    assert interests[1]["topic"] == "量子力学"

    data.decay_interests(decay_rate=0.1)
    interests = data.get_interests()
    assert interests[0]["weight"] == 0.8
    assert interests[1]["weight"] == 0.4

    data.decay_interests(decay_rate=0.35)
    interests = data.get_interests()
    assert len(interests) == 1
    assert interests[0]["topic"] == "宇宙の起源"
    assert interests[0]["weight"] == 0.45
