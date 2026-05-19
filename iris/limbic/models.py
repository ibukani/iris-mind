from __future__ import annotations

from dataclasses import dataclass, field
import math
import time


@dataclass
class EmotionState:
    """PAD (Pleasure-Arousal-Dominance) 3次元感情状態。

    Reference:
      Mehrabian, A. (1996). Pleasure-arousal-dominance: A general framework
      for describing and measuring individual differences in temperament.

    Attributes:
        valence:   快-不快 (-1.0=不快, 0.0=中立, 1.0=快)
        arousal:   覚醒度 (0.0=鎮静, 1.0=興奮)
        dominance: 支配性 (0.0=無力, 1.0=支配)
        updated_at: 最終更新時刻 (time.time)
    """

    valence: float = 0.0
    arousal: float = 0.0
    dominance: float = 0.5
    updated_at: float = field(default_factory=time.time)

    def decay(self, dt: float | None = None) -> None:
        """時間経過による感情の自然減衰（指数関数的）。
        arousal は早く減衰し、valence は比較的持続する。
        """
        if dt is None:
            dt = time.time() - self.updated_at
        if dt <= 0:
            return
        minutes = dt / 60.0
        lambda_v = 0.05
        lambda_a = 0.10
        lambda_d = 0.03
        self.valence *= math.exp(-lambda_v * minutes)
        self.arousal *= math.exp(-lambda_a * minutes)
        self.dominance = 0.5 + (self.dominance - 0.5) * math.exp(-lambda_d * minutes)
        self._clamp()

    def apply(self, delta: EmotionDelta, intensity: float = 1.0) -> None:
        """感情変化量を適用する。"""
        self.valence += delta.valence * intensity
        self.arousal += delta.arousal * intensity
        self.dominance += delta.dominance * intensity
        self._clamp()
        self.updated_at = time.time()

    def _clamp(self) -> None:
        self.valence = max(-1.0, min(1.0, self.valence))
        self.arousal = max(0.0, min(1.0, self.arousal))
        self.dominance = max(0.0, min(1.0, self.dominance))

    def to_dict(self) -> dict[str, float]:
        return {
            "valence": round(self.valence, 3),
            "arousal": round(self.arousal, 3),
            "dominance": round(self.dominance, 3),
        }


@dataclass
class EmotionDelta:
    """扁桃体が出力する感情変化量。"""

    valence: float = 0.0
    arousal: float = 0.0
    dominance: float = 0.0

    def scale(self, factor: float) -> EmotionDelta:
        return EmotionDelta(
            valence=self.valence * factor,
            arousal=self.arousal * factor,
            dominance=self.dominance * factor,
        )


BASIC_EMOTIONS: dict[str, EmotionDelta] = {
    "joy": EmotionDelta(valence=0.8, arousal=0.6, dominance=0.5),
    "sadness": EmotionDelta(valence=-0.7, arousal=-0.4, dominance=-0.3),
    "anger": EmotionDelta(valence=-0.5, arousal=0.8, dominance=0.7),
    "fear": EmotionDelta(valence=-0.6, arousal=0.7, dominance=-0.6),
    "surprise": EmotionDelta(valence=0.0, arousal=0.8, dominance=-0.2),
    "trust": EmotionDelta(valence=0.7, arousal=-0.1, dominance=0.4),
    "anticipation": EmotionDelta(valence=0.4, arousal=0.6, dominance=0.2),
    "calmness": EmotionDelta(valence=0.3, arousal=-0.6, dominance=0.1),
}
