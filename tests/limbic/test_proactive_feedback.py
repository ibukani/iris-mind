from iris.event.event_types import ProactiveResultEvent
from iris.limbic.manager import LimbicManager


def test_proactive_result_success_feedback():
    limbic = LimbicManager(event_bus=None)

    # 状態の初期化
    limbic._emotion.arousal = 0.5
    limbic._emotion.valence = -0.5
    limbic._emotion.dominance = -0.5
    limbic._drive.curiosity = 0.8
    initial_emotion = limbic.current_emotion().to_dict()
    initial_drive = limbic.current_drive().to_dict()

    # 成功イベントを発行したと仮定してハンドラを直接呼ぶ
    event = ProactiveResultEvent(timestamp=None, source="test", topic="test_topic", success=True, content="Success")
    limbic._on_proactive_result(event)

    new_emotion = limbic.current_emotion().to_dict()
    new_drive = limbic.current_drive().to_dict()

    # valence, dominanceが増加し、arousalが減少しているはず
    assert new_emotion["valence"] > initial_emotion["valence"]
    assert new_emotion["dominance"] > initial_emotion["dominance"]
    assert new_emotion["arousal"] < initial_emotion["arousal"]

    # Curiosityが満たされているはず (driveが減る)
    assert new_drive["curiosity"] < initial_drive["curiosity"]


def test_proactive_result_failure_feedback():
    limbic = LimbicManager(event_bus=None)

    initial_emotion = limbic.current_emotion().to_dict()

    # 失敗イベントを発行
    event = ProactiveResultEvent(timestamp=None, source="test", topic="test_topic", success=False, content="Failed")
    limbic._on_proactive_result(event)

    new_emotion = limbic.current_emotion().to_dict()

    # valence, dominanceが減少し、arousalが増加しているはず
    assert new_emotion["valence"] < initial_emotion["valence"]
    assert new_emotion["dominance"] < initial_emotion["dominance"]
    assert new_emotion["arousal"] > initial_emotion["arousal"]
