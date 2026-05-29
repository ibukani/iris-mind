from __future__ import annotations

import math
import time

from .models import CompanionEmotion, Mood

# 時間減衰定数 (秒)
_MOOD_DECAY_HALF_LIFE = 600.0  # 10分で半減
_BASELINE_RETURN_RATE = 0.05  # ベースラインへの復帰速度


class MoodDynamics:
    """slow-moving baseline: 会話による感情の累積影響と時間減衰"""

    def __init__(self) -> None:
        self._mood = Mood()
        self._last_update = time.time()

    def update(self, current_emotion: CompanionEmotion) -> Mood:
        """新しい感情をmoodに統合し、更新されたmoodを返す"""
        now = time.time()
        dt = now - self._last_update
        self._last_update = now

        decay = self._compute_decay(dt)
        self._mood.valence = self._mood.valence * decay + current_emotion.valence * current_emotion.intensity * (
            1 - decay
        )
        self._mood.arousal = self._mood.arousal * decay + current_emotion.arousal * current_emotion.intensity * (
            1 - decay
        )
        self._mood.dominance = self._mood.dominance * decay + current_emotion.dominance * current_emotion.intensity * (
            1 - decay
        )

        self._mood.valence = max(-1.0, min(1.0, self._mood.valence))
        self._mood.arousal = max(-1.0, min(1.0, self._mood.arousal))
        self._mood.dominance = max(-1.0, min(1.0, self._mood.dominance))
        self._mood.last_updated = now

        return Mood(
            valence=self._mood.valence,
            arousal=self._mood.arousal,
            dominance=self._mood.dominance,
            last_updated=now,
        )

    def get_mood(self) -> Mood:
        now = time.time()
        dt = now - self._last_update
        decay = self._compute_decay(dt)
        return Mood(
            valence=self._mood.valence * decay,
            arousal=self._mood.arousal * decay,
            dominance=self._mood.dominance * decay,
            last_updated=now,
        )

    def _compute_decay(self, dt: float) -> float:
        return math.exp(-0.693 * dt / _MOOD_DECAY_HALF_LIFE)

    def get_state(self) -> dict[str, float]:
        mood = self.get_mood()
        return mood.to_dict()
