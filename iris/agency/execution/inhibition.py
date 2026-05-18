from __future__ import annotations

from dataclasses import dataclass
import logging
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from iris.limbic.models import EmotionState

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


@dataclass
class GateVerdict:
    """基底核のゲート判定結果。

    脳: 大脳基底核は直接路 (Go) と間接路 (No-go) の2経路で行動を制御する。

    - suppressed: 間接路による完全抑制（クールダウン中 or スリープ中）
    - score: 抑制の強度（mood / confirmation / recent_activity の最小値 =  weakest link）
    - go_signal: 直接路の活性度（行動を起こす積極性。0.0=消極的, 1.0=積極的）
    - reason: 抑制の原因となった因子名
    """

    suppressed: bool
    score: float
    reason: str
    go_signal: float = 1.0


class InhibitionController:
    """基底核 (basal ganglia) に対応する抑制制御。

    脳: 大脳基底核は PFC からの計画を受け、直接路 (Go) と間接路 (No-go) の
    バランスで行動の開始/抑制を決定する。

    本クラスは主に間接路（抑制系）を担当:
    - mood（扁桃体からの感情入力→負の感情が強いほど抑制）
    - confirmation（連続無視→確認モード→抑制）
    - recent_activity（直近のユーザー活動→活動直後は抑制）
    - cooldown/sleep（外部からの強制抑制）

    Go信号（直接路）は PlanningManager の ProactiveScoring と統合して判定。
    """

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
        logger.debug("User activity recorded: last_user_activity=%.3f", self._last_user_activity)

    def check_ignore(self) -> None:
        if self._last_proactive_time == 0 or self._ignore_recorded:
            return
        if self._last_proactive_time > self._last_user_activity:
            self._consecutive_ignores += 1
            self._ignore_recorded = True
            logger.debug("Ignore detected: consecutive_ignores=%d", self._consecutive_ignores)
            if self._consecutive_ignores >= 2:
                self._confirmation_mode = True
                logger.info("Entered confirmation mode (ignores=%d)", self._consecutive_ignores)

    def evaluate(self, now: float) -> GateVerdict:
        if now < self._cooldown_until or self._is_sleeping:
            logger.debug(
                "Gate suppressed: cooldown_or_sleep (now=%.3f, cooldown_until=%.3f)", now, self._cooldown_until
            )
            return GateVerdict(suppressed=True, score=0.0, reason="cooldown_or_sleep", go_signal=0.0)

        factors: list[tuple[str, float]] = []

        mood_ok = 1.0 - self._negative_mood_score
        factors.append(("mood", max(0.0, mood_ok)))

        if self._confirmation_mode:
            factors.append(("confirmation", 0.3))
        else:
            factors.append(("confirmation", 1.0))

        if self._last_user_activity > 0:
            elapsed = now - self._last_user_activity
            if elapsed < 10:
                factors.append(("recent_activity", 1.0))
            elif elapsed < 60:
                factors.append(("recent_activity", 0.8))
            else:
                factors.append(("recent_activity", 0.5))
        else:
            factors.append(("recent_activity", 0.5))

        score = min(f[1] for f in factors)
        low = [f[0] for f in factors if f[1] < 0.5]
        reason = ", ".join(low) if low else "open"

        go_signal = self._compute_go_signal(now)
        logger.debug("Gate: factors=%s score=%.3f reason=%s go_signal=%.3f", factors, score, reason, go_signal)
        return GateVerdict(suppressed=False, score=score, reason=reason, go_signal=go_signal)

    def _compute_go_signal(self, now: float) -> float:
        if self._last_user_activity > 0:
            elapsed = now - self._last_user_activity
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
        mood_penalty = self._negative_mood_score * 0.5
        go *= max(0.1, 1.0 - mood_penalty)
        return round(go, 2)

    def is_suppressed(self, now: float) -> bool:
        return now < self._cooldown_until or self._is_sleeping

    def record_proactive_attempt(self) -> None:
        self._last_proactive_time = time.time()
        logger.debug("Proactive attempt recorded: last_proactive_time=%.3f", self._last_proactive_time)

    def notify_positive_response(self) -> None:
        self._consecutive_ignores = 0
        self._confirmation_mode = False

    def apply_frequency_penalty(self, degree: int) -> None:
        if degree <= 0:
            return
        base_cooldown = 600.0
        extra = base_cooldown * (2**degree - 1)
        self._cooldown_until = time.time() + extra
        self._negative_mood_score = min(1.0, degree * 0.15)
        logger.info(
            "Frequency penalty applied: degree=%d cooldown=%.0fs mood=%.2f",
            degree,
            extra,
            self._negative_mood_score,
        )

    def set_cooldown(self, duration_sec: float = 600.0) -> None:
        self._cooldown_until = time.time() + duration_sec
        logger.info("Proactive cooldown set for %.0f seconds", duration_sec)

    def set_mood(self, negative_score: float) -> None:
        self._negative_mood_score = max(0.0, min(1.0, negative_score))

    def apply_limbic_modulation(self, emotion: EmotionState) -> None:
        """Limbic 系の PAD 感情状態から抑制を直接変調する。

        Phase 4: 扁桃体からの感情入力を基底核抑制に直接反映。
        - valence < -0.3 → 負の感情が抑制を強める
        - arousal > 0.6  → 興奮は Go 信号を強化 (抑制弱める)
        - dominance < 0.3 → 無力感は抑制を強める
        """
        mood = 0.0
        if emotion.valence < -0.3:
            mood += abs(emotion.valence) * 0.4
        elif emotion.valence > 0.3:
            mood -= emotion.valence * 0.1

        if emotion.arousal > 0.6:
            mood -= emotion.arousal * 0.1
        elif emotion.arousal < 0.2:
            mood += 0.1

        if emotion.dominance < 0.3:
            mood += (0.3 - emotion.dominance) * 0.3
        elif emotion.dominance > 0.7:
            mood -= emotion.dominance * 0.05

        current = self._negative_mood_score
        self._negative_mood_score = max(0.0, min(1.0, current + mood))

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

    @property
    def last_proactive_time(self) -> float:
        return self._last_proactive_time

    @property
    def last_user_activity(self) -> float:
        return self._last_user_activity

    @property
    def negative_mood_score(self) -> float:
        return self._negative_mood_score
