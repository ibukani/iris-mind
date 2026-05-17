from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from iris.event.event_bus import EventBus
from iris.event.event import TimerTick
from iris.kernel.config import ProactiveConfig
from iris.memory.manager import MemoryManager

logger = logging.getLogger(__name__)

_NEGATIVE_RESPONSES = frozenset({
    "やめて", "静かに", "stop", "やめろ", "黙れ",
    "うるさい", "やめてください", "shut up",
})


@dataclass
class SuppressionState:
    last_proactive_time: float = 0.0
    last_user_activity: float = 0.0
    proactive_timestamps: list[float] = field(default_factory=list)
    consecutive_ignores: int = 0
    confirmation_mode: bool = False
    negative_mood_score: float = 0.0
    cooldown_until: float = 0.0
    is_sleeping: bool = False
    pending_proactive_time: float = 0.0


class ProactiveScorer:
    def __init__(
        self,
        config: ProactiveConfig,
        event_bus: EventBus,
        memory: MemoryManager,
        on_speak: Callable[[dict[str, float], float, str], None] | None = None,
    ) -> None:
        self._config = config
        self._memory = memory
        self._on_speak = on_speak
        self._event_bus = event_bus
        self._state = SuppressionState()
        self._last_check_time: float = 0.0
        self._ignore_recorded: bool = False

        if config.enabled:
            self._event_bus.subscribe("TimerTick", self._on_timer_tick)

    def set_on_speak(self, callback: Callable[[dict[str, float], float, str], None]) -> None:
        self._on_speak = callback

    def _on_timer_tick(self, _event: TimerTick) -> None:
        cfg = self._config
        if not cfg.enabled:
            return
        now = time.time()
        if now - self._last_check_time < cfg.check_interval_sec:
            return
        self._last_check_time = now
        self._check_ignore(now)
        total, scores = self._score_triggers(now)
        if total < cfg.speak_threshold:
            return
        trigger_type = max(scores, key=lambda k: scores[k])
        if self._on_speak:
            self._on_speak(scores, total, trigger_type)

    def _check_ignore(self, now: float) -> None:
        s = self._state
        if s.last_proactive_time == 0:
            return
        if self._ignore_recorded:
            return
        if s.last_proactive_time > s.last_user_activity:
            self._notify_ignore()
            self._ignore_recorded = True

    def _score_triggers(self, now: float) -> tuple[float, dict[str, float]]:
        w = self._config.trigger_weights
        time_score = self._compute_time_score(now)
        memory_score = self._compute_memory_score()
        context_score = self._compute_context_score()
        mood_score = self._compute_mood_score()
        total = (
            w.get("time", 0.25) * time_score
            + w.get("memory", 0.45) * memory_score
            + w.get("context", 0.15) * context_score
            + w.get("mood", 0.15) * mood_score
        )
        return total, {"time": time_score, "memory": memory_score, "context": context_score, "mood": mood_score}

    def _compute_time_score(self, now: float) -> float:
        s = self._state
        last_time = max(s.last_proactive_time, s.last_user_activity)
        if last_time == 0:
            return 0.4
        elapsed = now - last_time
        if elapsed < self._config.min_interval_sec:
            return 0.0
        ratio = (elapsed - self._config.min_interval_sec) / (self._config.max_interval_sec - self._config.min_interval_sec)
        return min(ratio, 1.0)

    def _compute_memory_score(self) -> float:
        try:
            recent = self._memory.get_recent(3)
            if not recent:
                return 0.0
            topic = " ".join(item.get("summary", "") for item in recent)
            if not topic.strip():
                return 0.0
            results = self._memory.search_semantic(topic, max_results=3)
            if results:
                return max(r.get("score", 0.0) for r in results)
        except Exception as e:
            logger.debug("Memory score failed: %s", e)
        return 0.0

    @staticmethod
    def _char_bigram_set(text: str) -> set[str]:
        return {text[i: i + 2] for i in range(len(text) - 1)}

    def _compute_context_score(self) -> float:
        try:
            recent = self._memory.get_recent(2)
            if len(recent) < 2:
                return 0.3
            summaries = [item.get("summary", "") for item in recent[-2:]]
            if all(len(s.strip()) < 10 for s in summaries):
                return 0.7
            bg_a = self._char_bigram_set(summaries[0])
            bg_b = self._char_bigram_set(summaries[1])
            if not bg_a and not bg_b:
                return 0.5
            if not bg_a or not bg_b:
                return 0.3
            jaccard = len(bg_a & bg_b) / len(bg_a | bg_b)
            return min(jaccard + 0.2, 1.0)
        except Exception:
            return 0.0

    def _compute_mood_score(self) -> float:
        neg = self._state.negative_mood_score
        if neg >= 0.7:
            return 0.0
        return max(0.0, 1.0 - neg)

    def _notify_ignore(self) -> None:
        s = self._state
        s.consecutive_ignores += 1
        if s.consecutive_ignores >= 2:
            s.confirmation_mode = True
            logger.info("Entered confirmation mode (ignores=%d)", s.consecutive_ignores)

    # === Public API for external interaction ===

    def notify_user_activity(self) -> None:
        self._state.last_user_activity = time.time()
        self._ignore_recorded = False

    def on_user_response(self, content: str) -> None:
        s = self._state
        if s.pending_proactive_time == 0.0:
            return
        elapsed = time.time() - s.pending_proactive_time
        s.pending_proactive_time = 0.0
        if elapsed > 60.0:
            return
        if content.strip().lower() in _NEGATIVE_RESPONSES:
            self.set_cooldown(600.0)
        else:
            self.notify_positive_response()

    def notify_positive_response(self) -> None:
        self._state.consecutive_ignores = 0
        self._state.confirmation_mode = False

    def set_cooldown(self, duration_sec: float = 600.0) -> None:
        self._state.cooldown_until = time.time() + duration_sec
        logger.info("Proactive cooldown set for %.0f seconds", duration_sec)

    def set_mood(self, negative_score: float) -> None:
        self._state.negative_mood_score = max(0.0, min(1.0, negative_score))

    def reset(self) -> None:
        self._state = SuppressionState()
        self._ignore_recorded = False
        logger.info("Suppression state reset")

    def get_status(self) -> dict:
        s = self._state
        return {
            "enabled": self._config.enabled,
            "last_proactive_time": s.last_proactive_time,
            "last_user_activity": s.last_user_activity,
            "consecutive_ignores": s.consecutive_ignores,
            "confirmation_mode": s.confirmation_mode,
        }
