import time

from iris.agency.execution.inhibition import InhibitionController


def test_inhibition_topic_cooldown():
    inhibition = InhibitionController()
    now = time.time()

    # 最初は抑制されていない
    assert not inhibition.is_topic_suppressed("search_topic", now)

    # 記録する
    inhibition.record_topic("search_topic", 3600.0)

    # 抑制されるはず
    assert inhibition.is_topic_suppressed("search_topic", now)
    assert inhibition.is_topic_suppressed("search_topic", now + 1800)

    # 別のトピックは抑制されない
    assert not inhibition.is_topic_suppressed("other_topic", now)

    # 時間が経過したら抑制解除されるはず
    assert not inhibition.is_topic_suppressed("search_topic", now + 3601)
