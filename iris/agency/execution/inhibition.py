from __future__ import annotations

from dataclasses import dataclass, field
import logging
import time
from typing import TYPE_CHECKING, TypedDict

if TYPE_CHECKING:
    from iris.limbic.models import EmotionState

logger = logging.getLogger(__name__)


class InhibitionStatus(TypedDict):
    last_proactive_time: float
    last_user_activity: float
    consecutive_ignores: int
    confirmation_mode: bool


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


@dataclass
class GateVerdict:
    suppressed: bool
    score: float
    reason: str
    go_signal: float = 1.0


@dataclass
class _InhibitionState:
    last_proactive_time: float = 0.0
    last_user_activity: float = 0.0
    consecutive_ignores: int = 0
    confirmation_mode: bool = False
    negative_mood_score: float = 0.0
    cooldown_until: float = 0.0
    is_sleeping: bool = False
    ignore_recorded: bool = False
    generating: bool = False
    outputs_since_input: int = 0
    frequency_exceeded: bool = False
    topic_cooldowns: dict[str, float] = field(default_factory=dict)


class InhibitionController:
    def __init__(self) -> None:
        self._state = _InhibitionState()

    def set_generating(self, generating: bool) -> None:
        self._state.generating = generating
        logger.debug("InhibitionController: generating state set to %s", generating)

    def set_output_frequency_state(self, outputs_since_input: int, frequency_exceeded: bool) -> None:
        self._state.outputs_since_input = outputs_since_input
        self._state.frequency_exceeded = frequency_exceeded

    def notify_user_activity(self) -> None:
        self._state.last_user_activity = time.time()
        self._state.ignore_recorded = False
        self._state.consecutive_ignores = 0
        self._state.confirmation_mode = False
        logger.debug(
            "User activity recorded: last_user_activity=%.3f, ignores reset",
            self._state.last_user_activity,
        )

    def check_ignore(self) -> bool:
        s = self._state
        if s.last_proactive_time == 0:
            return False
        if s.last_proactive_time > s.last_user_activity and not s.ignore_recorded:
            s.consecutive_ignores += 1
            s.ignore_recorded = True
            if s.consecutive_ignores >= 2:
                s.confirmation_mode = True
                logger.info("Entered confirmation mode (ignores=%d)", s.consecutive_ignores)
            elif s.consecutive_ignores >= 3:
                logger.info(
                    "Extended ignore detected: %d consecutive ignores",
                    s.consecutive_ignores,
                )
            logger.debug("Ignore detected: consecutive_ignores=%d", s.consecutive_ignores)
            return True
        return False

    def evaluate(self, now: float) -> GateVerdict:
        s = self._state
        if s.generating:
            logger.debug("Gate suppressed: active generation in progress")
            return GateVerdict(suppressed=True, score=0.0, reason="generating", go_signal=0.0)

        if now < s.cooldown_until or s.is_sleeping:
            logger.debug("Gate suppressed: cooldown_or_sleep (now=%.3f, cooldown_until=%.3f)", now, s.cooldown_until)
            return GateVerdict(suppressed=True, score=0.0, reason="cooldown_or_sleep", go_signal=0.0)

        if s.consecutive_ignores >= 3:
            logger.debug("Gate suppressed: consecutive_ignores=%d >= 3", s.consecutive_ignores)
            return GateVerdict(suppressed=True, score=0.0, reason=f"ignored_x{s.consecutive_ignores}", go_signal=0.0)

        factors = self._build_factor_list(now)
        score = min(f[1] for f in factors)
        low = [f[0] for f in factors if f[1] < 0.5]
        reason = ", ".join(low) if low else "open"

        go_signal = self._compute_go_signal(now)
        logger.debug("Gate: factors=%s score=%.3f reason=%s go_signal=%.3f", factors, score, reason, go_signal)
        return GateVerdict(suppressed=False, score=score, reason=reason, go_signal=go_signal)

    def _build_factor_list(self, now: float) -> list[tuple[str, float]]:
        s = self._state
        factors: list[tuple[str, float]] = []

        mood_ok = 1.0 - s.negative_mood_score
        factors.append(("mood", max(0.0, mood_ok)))

        if s.confirmation_mode:
            c_factor = max(0.1, 0.4 - s.consecutive_ignores * 0.1)
            factors.append(("confirmation", c_factor))
        else:
            factors.append(("confirmation", 1.0))

        factors.append(("recent_activity", self._compute_recent_activity_factor(now)))
        factors.append(("output_frequency", self._compute_output_frequency_factor()))
        return factors

    def _compute_recent_activity_factor(self, now: float) -> float:
        s = self._state
        if s.last_user_activity <= 0:
            return 0.5
        elapsed = now - s.last_user_activity
        if elapsed < 10:
            return 1.0
        if elapsed < 60:
            return 0.8
        return 0.5

    def _compute_output_frequency_factor(self) -> float:
        s = self._state
        if s.frequency_exceeded:
            return 0.3
        if s.outputs_since_input >= 4:
            return 0.2
        if s.outputs_since_input >= 3:
            return 0.5
        if s.outputs_since_input >= 1:
            return 0.8
        return 1.0

    def _compute_go_signal(self, now: float) -> float:
        s = self._state
        if s.last_user_activity > 0:
            elapsed = now - s.last_user_activity
            if elapsed < 10:
                go = 0.3
            elif elapsed < 60:
                go = 0.5
            elif elapsed < 300:
                go = 0.7
            else:
                go = 1.0
        else:
            go = 0.5
        mood_penalty = s.negative_mood_score * 0.5
        go *= max(0.1, 1.0 - mood_penalty)
        return round(go, 2)

    def is_suppressed(self, now: float) -> bool:
        s = self._state
        return now < s.cooldown_until or s.is_sleeping

    def record_proactive_attempt(self) -> None:
        self._state.last_proactive_time = time.time()
        self._state.ignore_recorded = False
        logger.debug("Proactive attempt recorded: last_proactive_time=%.3f", self._state.last_proactive_time)

    def notify_positive_response(self) -> None:
        self._state.consecutive_ignores = 0
        self._state.confirmation_mode = False

    def apply_frequency_penalty(self, degree: int) -> None:
        if degree <= 0:
            return
        s = self._state
        base_cooldown = 600.0
        extra = base_cooldown * (2**degree - 1)
        s.cooldown_until = time.time() + extra
        s.negative_mood_score = min(1.0, s.negative_mood_score + degree * 0.15)
        logger.info(
            "Frequency penalty applied: degree=%d cooldown=%.0fs mood=%.2f",
            degree,
            extra,
            s.negative_mood_score,
        )

    def set_cooldown(self, duration_sec: float = 600.0) -> None:
        self._state.cooldown_until = time.time() + duration_sec
        logger.info("Proactive cooldown set for %.0f seconds", duration_sec)

    def record_topic(self, topic: str, duration_sec: float = 3600.0) -> None:
        if not topic:
            return
        self._state.topic_cooldowns[topic] = time.time() + duration_sec
        logger.info("Topic cooldown set for '%s' for %.0f seconds", topic, duration_sec)

    def is_topic_suppressed(self, topic: str, now: float) -> bool:
        if not topic:
            return False
        cooldown_until = self._state.topic_cooldowns.get(topic, 0.0)
        return now < cooldown_until

    def set_mood(self, negative_score: float) -> None:
        self._state.negative_mood_score = max(0.0, min(1.0, negative_score))

    def apply_limbic_modulation(self, emotion: EmotionState) -> None:
        mood = 0.0
        triggered = False

        if emotion.valence < -0.3:
            mood += abs(emotion.valence) * 0.4
            triggered = True
        elif emotion.valence > 0.3:
            mood -= emotion.valence * 0.1
            triggered = True

        if emotion.arousal > 0.6:
            mood -= emotion.arousal * 0.1
            triggered = True
        elif emotion.arousal < 0.2:
            mood += 0.1
            triggered = True

        if emotion.dominance < 0.3:
            mood += (0.3 - emotion.dominance) * 0.3
            triggered = True
        elif emotion.dominance > 0.7:
            mood -= emotion.dominance * 0.05
            triggered = True

        current = self._state.negative_mood_score

        if not triggered and current > 0:
            decay = max(current * 0.1, 0.02)
            current = max(0.0, current - decay)

        self._state.negative_mood_score = max(0.0, min(1.0, current + mood))

    def reset(self) -> None:
        self._state = _InhibitionState()
        logger.info("Inhibition state reset")

    def get_status(self) -> InhibitionStatus:
        return {
            "last_proactive_time": self._state.last_proactive_time,
            "last_user_activity": self._state.last_user_activity,
            "consecutive_ignores": self._state.consecutive_ignores,
            "confirmation_mode": self._state.confirmation_mode,
        }

    @property
    def last_proactive_time(self) -> float:
        return self._state.last_proactive_time

    @property
    def last_user_activity(self) -> float:
        return self._state.last_user_activity

    @property
    def negative_mood_score(self) -> float:
        return self._state.negative_mood_score

    @property
    def consecutive_ignores(self) -> int:
        return self._state.consecutive_ignores

    @property
    def outputs_since_input(self) -> int:
        return self._state.outputs_since_input

    @property
    def frequency_exceeded(self) -> bool:
        return self._state.frequency_exceeded

    @property
    def confirmation_mode(self) -> bool:
        return self._state.confirmation_mode
