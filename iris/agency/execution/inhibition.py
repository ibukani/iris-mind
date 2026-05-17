from __future__ import annotations

import logging
import time

logger = logging.getLogger(__name__)

_NEGATIVE_RESPONSES = frozenset(
    {
        "やめて",
        "静かに",
        "stop",
        "やめろ",
        "黙れ",
        "うるさい",
        "やめてください",
        "shut up",
    }
)


class InhibitionController:
    def __init__(self) -> None:
        self._last_proactive_time: float = 0.0
        self._last_user_activity: float = 0.0
        self._consecutive_ignores: int = 0
        self._confirmation_mode: bool = False
        self._negative_mood_score: float = 0.0
        self._cooldown_until: float = 0.0
        self._is_sleeping: bool = False
        self._ignore_recorded: bool = False

    def notify_user_activity(self) -> None:
        self._last_user_activity = time.time()
        self._ignore_recorded = False

    def check_ignore(self) -> None:
        if self._last_proactive_time == 0 or self._ignore_recorded:
            return
        if self._last_proactive_time > self._last_user_activity:
            self._consecutive_ignores += 1
            self._ignore_recorded = True
            if self._consecutive_ignores >= 2:
                self._confirmation_mode = True
                logger.info("Entered confirmation mode (ignores=%d)", self._consecutive_ignores)

    def is_suppressed(self, now: float) -> bool:
        return now < self._cooldown_until or self._is_sleeping

    def record_proactive_attempt(self) -> None:
        self._last_proactive_time = time.time()

    def notify_positive_response(self) -> None:
        self._consecutive_ignores = 0
        self._confirmation_mode = False

    def set_cooldown(self, duration_sec: float = 600.0) -> None:
        self._cooldown_until = time.time() + duration_sec
        logger.info("Proactive cooldown set for %.0f seconds", duration_sec)

    def set_mood(self, negative_score: float) -> None:
        self._negative_mood_score = max(0.0, min(1.0, negative_score))

    def reset(self) -> None:
        self._last_proactive_time = 0.0
        self._last_user_activity = 0.0
        self._consecutive_ignores = 0
        self._confirmation_mode = False
        self._negative_mood_score = 0.0
        self._cooldown_until = 0.0
        self._is_sleeping = False
        self._ignore_recorded = False
        logger.info("Inhibition state reset")

    def get_status(self) -> dict:
        return {
            "last_proactive_time": self._last_proactive_time,
            "last_user_activity": self._last_user_activity,
            "consecutive_ignores": self._consecutive_ignores,
            "confirmation_mode": self._confirmation_mode,
        }

    # Properties for Scoring consumption
    @property
    def last_proactive_time(self) -> float:
        return self._last_proactive_time

    @property
    def last_user_activity(self) -> float:
        return self._last_user_activity

    @property
    def negative_mood_score(self) -> float:
        return self._negative_mood_score
