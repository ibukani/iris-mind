from __future__ import annotations

import logging
import time
from collections.abc import Callable

from iris.agency.execution.inhibition import InhibitionController
from iris.agency.planning.scoring import ProactiveScoring
from iris.event.event_bus import EventBus
from iris.event.event_types import TimerTick
from iris.kernel.config import ProactiveConfig

logger = logging.getLogger(__name__)


class TimerGate:
    def __init__(
        self,
        config: ProactiveConfig,
        event_bus: EventBus,
        scoring: ProactiveScoring,
        inhibition: InhibitionController,
        on_speak: Callable[[dict[str, float], float], None] | None = None,
    ) -> None:
        self._config = config
        self._scoring = scoring
        self._inhibition = inhibition
        self._on_speak = on_speak
        self._last_check_time: float = 0.0

        if config.enabled:
            event_bus.subscribe("TimerTick", self._on_timer_tick)

    def set_on_speak(self, callback: Callable[[dict[str, float], float], None]) -> None:
        self._on_speak = callback

    def _on_timer_tick(self, _event: TimerTick) -> None:
        cfg = self._config
        if not cfg.enabled:
            return
        now = time.time()
        if now - self._last_check_time < cfg.check_interval_sec:
            return
        self._last_check_time = now

        self._inhibition.check_ignore()
        if self._inhibition.is_suppressed(now):
            return

        total, scores = self._scoring.compute(
            now,
            self._inhibition.last_proactive_time,
            self._inhibition.last_user_activity,
            self._inhibition.negative_mood_score,
        )
        if total < cfg.speak_threshold:
            return

        self._inhibition.record_proactive_attempt()
        if self._on_speak:
            self._on_speak(scores, total)
