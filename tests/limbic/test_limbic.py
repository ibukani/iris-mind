from iris.limbic.manager import LimbicManager


def test_build_response_style_neutral() -> None:
    manager = LimbicManager(event_bus=None)
    # 中立状態
    style = manager.generate_response_style()
    assert style == ""


def test_generate_response_style_joy():
    manager = LimbicManager(event_bus=None)
    # 快・興奮状態
    manager._emotion.valence = 0.8
    manager._emotion.arousal = 0.6
    style = manager.generate_response_style()
    assert "明るく温かいトーン" in style
    assert "やったー！" in style


def test_generate_response_style_anger():
    manager = LimbicManager(event_bus=None)
    # 不快・興奮（イライラ）状態
    manager._emotion.valence = -0.8
    manager._emotion.arousal = 0.6
    style = manager.generate_response_style()
    assert "最小限の言葉" in style
    assert "はぁ…" in style


def test_generate_response_style_sadness():
    manager = LimbicManager(event_bus=None)
    # 不快・鎮静（悲しい）状態
    manager._emotion.valence = -0.4
    manager._emotion.arousal = 0.1
    style = manager.generate_response_style()
    assert "短い言葉で応答" in style
    assert "うう…" in style
