from __future__ import annotations

from iris.memory.persona_data import PersonaData
from iris.memory.persona_profile import PersonaProfile


def _make_profile() -> PersonaProfile:
    return PersonaProfile(persona_data=PersonaData())


def test_empty_profile() -> None:
    profile = _make_profile()
    assert profile.get_speech_style() == ""
    assert profile.get_traits() == ""


def test_update_from_reflection() -> None:
    profile = _make_profile()
    reflection = {
        "speech_style": "カジュアルで親しみやすい",
        "expressed_traits": "好奇心旺盛・協力的",
        "user_reaction": "好意的",
    }
    profile.update_from_reflection(reflection)
    assert "カジュアル" in profile.get_speech_style()
    assert "好奇心旺盛" in profile.get_traits()


def test_set_speech_style() -> None:
    profile = _make_profile()
    profile.set_speech_style("フォーマル")
    assert "- フォーマル" in profile.get_speech_style()


def test_set_traits() -> None:
    profile = _make_profile()
    profile.set_traits("論理的・分析的")
    assert "- 論理的" in profile.get_traits()


def test_reset() -> None:
    profile = _make_profile()
    profile.set_speech_style("test")
    profile.set_traits("test")
    profile.reset()
    assert profile.get_speech_style() == ""
    assert profile.get_traits() == ""


def test_update_from_reflection_empty() -> None:
    profile = _make_profile()
    profile.update_from_reflection({})
    assert profile.get_speech_style() == ""
    assert profile.get_traits() == ""
