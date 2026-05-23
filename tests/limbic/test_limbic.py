from iris.limbic.models import EmotionState
from iris.limbic.mood import MoodEngine


def _engine() -> MoodEngine:
    return MoodEngine()


def test_build_response_style_neutral() -> None:
    e = EmotionState()
    style = _engine().generate_response_style(e)
    assert style == ""


def test_generate_response_style_joy() -> None:
    e = EmotionState(valence=0.8, arousal=0.6)
    style = _engine().generate_response_style(e)
    assert "明るく温かいトーン" in style
    assert "やったー！" in style


def test_generate_response_style_anger() -> None:
    e = EmotionState(valence=-0.8, arousal=0.6)
    style = _engine().generate_response_style(e)
    assert "最小限の言葉" in style
    assert "はぁ…" in style


def test_generate_response_style_sadness() -> None:
    e = EmotionState(valence=-0.4, arousal=0.1)
    style = _engine().generate_response_style(e)
    assert "短い言葉で応答" in style
    assert "うう…" in style
