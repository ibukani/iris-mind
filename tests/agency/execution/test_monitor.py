from __future__ import annotations

from collections.abc import Callable

import pytest

from iris.agency import OutputTracker


@pytest.fixture
def mock_time() -> Callable[[], float]:
    t: float = 1000.0

    def _time() -> float:
        nonlocal t
        current = t
        t += 1.0
        return current

    return _time


def test_record_output_tracks_window(mock_time: Callable[[], float]) -> None:
    monitor = OutputTracker(internal_bus=None, talkative_threshold=5, time_provider=mock_time)  # type: ignore[arg-type]
    for _ in range(6):
        monitor.record_output()
    assert monitor.output_count_5min == 6


def test_frequency_exceeded_flag(mock_time: Callable[[], float]) -> None:
    monitor = OutputTracker(internal_bus=None, max_per_5min=3, talkative_threshold=10, time_provider=mock_time)  # type: ignore[arg-type]
    assert "frequency_exceeded" not in monitor.record_output()
    assert "frequency_exceeded" not in monitor.record_output()
    assert "frequency_exceeded" in monitor.record_output()


def test_talkative_flag(mock_time: Callable[[], float]) -> None:
    monitor = OutputTracker(internal_bus=None, talkative_threshold=3, time_provider=mock_time)  # type: ignore[arg-type]
    assert "talkative" not in monitor.record_output()
    assert "talkative" not in monitor.record_output()
    flags = monitor.record_output()
    assert "talkative" in flags


def test_talkative_degree(mock_time: Callable[[], float]) -> None:
    monitor = OutputTracker(internal_bus=None, talkative_threshold=3, time_provider=mock_time)  # type: ignore[arg-type]
    assert monitor.talkative_degree == 0
    monitor.record_output()
    assert monitor.talkative_degree == 0
    monitor.record_output()
    assert monitor.talkative_degree == 0
    monitor.record_output()  # 3rd output = threshold = degree 1
    assert monitor.talkative_degree == 1
    monitor.record_output()  # 4th = degree 2
    assert monitor.talkative_degree == 2
    monitor.record_output()  # 5th = degree 3
    assert monitor.talkative_degree == 3
    for _ in range(10):
        monitor.record_output()
    assert monitor.talkative_degree == 5  # capped at _MAX_SUPPRESSION_DEGREE


def test_record_user_input_resets_talkative(mock_time: Callable[[], float]) -> None:
    monitor = OutputTracker(internal_bus=None, talkative_threshold=3, time_provider=mock_time)  # type: ignore[arg-type]
    monitor.record_output()
    monitor.record_output()
    flags = monitor.record_output()
    assert "talkative" in flags
    assert monitor.talkative_degree == 1

    monitor.record_user_input()
    assert monitor.talkative_degree == 0
    assert monitor.outputs_since_last_input == 0

    flags = monitor.record_output()
    assert "talkative" not in flags


def test_reset(mock_time: Callable[[], float]) -> None:
    monitor = OutputTracker(internal_bus=None, talkative_threshold=2, time_provider=mock_time)  # type: ignore[arg-type]
    monitor.record_output()
    monitor.record_output()
    assert monitor.alert_count > 0 or monitor.talkative_degree > 0
    monitor.reset()
    assert monitor.alert_count == 0
    assert monitor.talkative_degree == 0
    assert monitor.outputs_since_last_input == 0
