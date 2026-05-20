from __future__ import annotations

from collections import deque
from collections.abc import Callable
import logging
import time

from iris.agency.bus import InternalBus

logger = logging.getLogger(__name__)


_TALKATIVE_THRESHOLD = 3
_MAX_SUPPRESSION_DEGREE = 5


class OutputMonitor:
    def __init__(
        self,
        internal_bus: InternalBus,
        max_per_5min: int = 5,
        talkative_threshold: int = _TALKATIVE_THRESHOLD,
        time_provider: Callable[[], float] | None = None,
    ) -> None:
        self._bus = internal_bus
        self._max_per_5min = max_per_5min
        self._talkative_threshold = talkative_threshold
        self._time = time_provider or time.time
        self._window: deque[float] = deque()
        self._alert_count: int = 0
        self._outputs_since_input: int = 0
        self._valence: float = 0.0
        self._arousal: float = 0.0
        self._dominance: float = 0.5

    def set_emotion_state(self, valence: float, arousal: float, dominance: float) -> None:
        self._valence = valence
        self._arousal = arousal
        self._dominance = dominance

    def _get_effective_talkative_threshold(self) -> int:
        t = self._talkative_threshold
        if self._valence >= 0.3:
            t += 2
        elif self._valence <= -0.3:
            t -= 1
        if self._dominance < 0.3:
            t -= 2
        return max(1, t)

    def _get_effective_max_per_5min(self) -> int:
        m = self._max_per_5min
        if self._valence >= 0.3:
            m += 2
        elif self._valence <= -0.3:
            m -= 1
        if self._dominance < 0.3:
            m -= 2
        if self._arousal > 0.6:
            m = 999
        return max(1, m)

    def record_user_input(self) -> None:
        self._outputs_since_input = 0
        logger.debug("OutputMonitor: user input recorded, reset outputs_since_input")

    def record_output(self) -> list[str]:
        now = self._time()
        self._window.append(now)
        while self._window and now - self._window[0] > 300:
            self._window.popleft()

        self._outputs_since_input += 1

        flags: list[str] = []
        if len(self._window) >= self._get_effective_max_per_5min():
            flags.append("frequency_exceeded")
            self._alert_count += 1
            logger.warning(
                "OutputMonitor: frequency exceeded (%d in 5min, alert #%d) emotion=(v=%.2f a=%.2f d=%.2f)",
                len(self._window),
                self._alert_count,
                self._valence,
                self._arousal,
                self._dominance,
            )
        if self._outputs_since_input >= self._get_effective_talkative_threshold():
            flags.append("talkative")
            logger.info(
                "OutputMonitor: talkative (%d outputs since last user input, threshold=%d)",
                self._outputs_since_input,
                self._get_effective_talkative_threshold(),
            )
        return flags

    @property
    def talkative_degree(self) -> int:
        threshold = self._get_effective_talkative_threshold()
        degree = self._outputs_since_input - threshold + 1
        if degree < 0:
            return 0
        return min(degree, _MAX_SUPPRESSION_DEGREE)

    def check_health(self) -> list[dict]:
        issues: list[dict] = []
        if self._alert_count > 0:
            issues.append(
                {
                    "type": "output_monitor",
                    "alert_count": self._alert_count,
                    "output_5min": self.output_count_5min,
                }
            )
        return issues

    @property
    def alert_count(self) -> int:
        return self._alert_count

    @property
    def output_count_5min(self) -> int:
        now = self._time()
        return sum(1 for t in self._window if now - t <= 300)

    @property
    def frequency_exceeded(self) -> bool:
        return self.output_count_5min >= self._get_effective_max_per_5min()

    @property
    def outputs_since_last_input(self) -> int:
        return self._outputs_since_input

    def reset(self) -> None:
        self._window.clear()
        self._alert_count = 0
        self._outputs_since_input = 0
