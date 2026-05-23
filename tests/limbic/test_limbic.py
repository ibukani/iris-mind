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
    assert any(
        x in style for x in ["明るく温かいトーン", "温かみのある明るい", "明るい声で", "最高に嬉しそう", "歓喜に満ちた"]
    )
    assert any(x in style for x in ["まじで！", "うそっ！", "最高！！", "うわぁぁ！", "興奮を隠しきれない", "元気よく"])


def test_generate_response_style_anger() -> None:
    e = EmotionState(valence=-0.8, arousal=0.6)
    style = _engine().generate_response_style(e)
    assert any(x in style for x in ["最小限の言葉", "短く応答", "ぶっきらぼう", "怒りや深い悲しみ", "深刻なトーン"])
    assert any(x in style for x in ["はぁ…", "もう！", "苛立った", "信じられない！", "最悪だ！", "怒りや絶望"])


def test_generate_response_style_sadness() -> None:
    e = EmotionState(valence=-0.4, arousal=0.1)
    style = _engine().generate_response_style(e)
    assert any(x in style for x in ["控えめに", "悲しそう"])
    assert any(x in style for x in ["うう…", "しゅん…", "沈んだ声"])
