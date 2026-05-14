from __future__ import annotations

import os
import tempfile
from pathlib import Path

from iris.memory.persona_data import PersonaData
from iris.memory.persona_profile import PersonaProfile


def _make_profile() -> tuple[PersonaProfile, str]:
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    os.unlink(path)
    data = PersonaData(path=path)
    return PersonaProfile(persona_data=data), path


def _clean(path: str) -> None:
    p = Path(path)
    if p.exists():
        os.unlink(path)


def test_empty_profile() -> None:
    profile, path = _make_profile()
    assert profile.get_speech_style() == ""
    assert profile.get_traits() == ""
    _clean(path)


def test_update_from_reflection() -> None:
    profile, path = _make_profile()
    reflection = {
        "speech_style": "カジュアルで親しみやすい",
        "expressed_traits": "好奇心旺盛・協力的",
        "user_reaction": "好意的",
    }
    profile.update_from_reflection(reflection)
    assert "カジュアル" in profile.get_speech_style()
    assert "好奇心旺盛" in profile.get_traits()
    _clean(path)


def test_set_speech_style() -> None:
    profile, path = _make_profile()
    profile.set_speech_style("フォーマル")
    assert "- フォーマル" in profile.get_speech_style()
    _clean(path)


def test_set_traits() -> None:
    profile, path = _make_profile()
    profile.set_traits("論理的・分析的")
    assert "- 論理的" in profile.get_traits()
    _clean(path)


def test_reset() -> None:
    profile, path = _make_profile()
    profile.set_speech_style("test")
    profile.set_traits("test")
    profile.reset()
    assert profile.get_speech_style() == ""
    assert profile.get_traits() == ""
    _clean(path)


def test_update_from_reflection_empty() -> None:
    profile, path = _make_profile()
    profile.update_from_reflection({})
    assert profile.get_speech_style() == ""
    assert profile.get_traits() == ""
    _clean(path)
