from __future__ import annotations

from collections.abc import Callable
import time

import pytest

from iris.agency import InhibitionController


@pytest.fixture
def mock_time() -> Callable[[], float]:
    t: float = 1000.0

    def _time() -> float:
        nonlocal t
        current = t
        t += 1.0
        return current

    return _time


def test_apply_frequency_penalty_sets_cooldown(mock_time: Callable[[], float]) -> None:
    controller = InhibitionController()
    controller.apply_frequency_penalty(2)

    now = time.time()
    verdict = controller.evaluate(now)
    assert verdict.suppressed
    assert "cooldown_or_sleep" in verdict.reason


def test_apply_frequency_penalty_sets_mood(mock_time: Callable[[], float]) -> None:
    controller = InhibitionController()
    controller.apply_frequency_penalty(4)

    assert controller.negative_mood_score == pytest.approx(0.6, abs=0.01)

    now = time.time()
    verdict = controller.evaluate(now)
    assert verdict.score <= 0.5


def test_apply_frequency_penalty_zero_degree_does_nothing(mock_time: Callable[[], float]) -> None:
    controller = InhibitionController()
    initial_mood = controller.negative_mood_score
    controller.apply_frequency_penalty(0)
    assert controller.negative_mood_score == initial_mood


def test_apply_frequency_penalty_caps_mood_at_one() -> None:
    controller = InhibitionController()
    controller.apply_frequency_penalty(10)
    assert controller.negative_mood_score == 1.0


def test_frequency_penalty_reduces_go_signal_indirectly(mock_time: Callable[[], float]) -> None:
    controller = InhibitionController()
    controller.notify_user_activity()

    normal = controller.evaluate(time.time())
    normal_go = normal.go_signal

    controller.apply_frequency_penalty(5)
    controller.notify_user_activity()
    penalized = controller.evaluate(time.time())

    assert penalized.go_signal < normal_go


def test_generating_suppresses_evaluate() -> None:
    controller = InhibitionController()
    controller.set_generating(True)
    verdict = controller.evaluate(time.time())
    assert verdict.suppressed
    assert verdict.reason == "generating"

    controller.set_generating(False)
    verdict = controller.evaluate(time.time())
    # generating 以外での抑制がなければ False
    assert not verdict.suppressed or verdict.reason != "generating"
