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
        valence_uncertainty:   valenceの不確実性/葛藤 (0.0=明確, 1.0=最大葛藤)
        arousal_uncertainty:   arousalの不確実性
        dominance_uncertainty: dominanceの不確実性
        updated_at: 最終更新時刻 (time.time)
    """

    valence: float = 0.0
    arousal: float = 0.0
    dominance: float = 0.5
    valence_uncertainty: float = 0.0
    arousal_uncertainty: float = 0.0
    dominance_uncertainty: float = 0.0
    updated_at: float = field(default_factory=time.time)

    def decay(self, dt: float | None = None) -> None:
        """時間経過による感情の自然減衰（指数関数的）。
        arousal は早く減衰し、valence は比較的持続する。
        60分以上の経過で強制的に中立化する。
        """
        if dt is None:
            dt = time.time() - self.updated_at
        if dt <= 0:
            return
        minutes = dt / 60.0
        if minutes >= 60:
            self.valence = 0.0
            self.arousal = 0.0
            self.dominance = 0.5
            self.valence_uncertainty = 1.0
            self.arousal_uncertainty = 1.0
            self.dominance_uncertainty = 1.0
            return
        lambda_v = 0.02
        lambda_a = 0.04
        lambda_d = 0.01
        self.valence *= math.exp(-lambda_v * minutes)
        self.arousal *= math.exp(-lambda_a * minutes)
        self.dominance = 0.5 + (self.dominance - 0.5) * math.exp(-lambda_d * minutes)
        # 不確実性は時間経過で上昇（記憶減衰）
        u_rate = 0.015
        self.valence_uncertainty = min(1.0, self.valence_uncertainty + u_rate * minutes)
        self.arousal_uncertainty = min(1.0, self.arousal_uncertainty + u_rate * minutes)
        self.dominance_uncertainty = min(1.0, self.dominance_uncertainty + u_rate * minutes)
        self._clamp()

    def apply(self, delta: EmotionDelta, intensity: float = 1.0) -> None:
        """感情変化量と不確実性を同時に適用する。

        量子認知: 新たな測定（感情刺激）が状態ベクトルを更新する。
        信号に葛藤があると不確実性が上昇（重ね合わせの拡大）、
        明確な信号は不確実性を減少させる（収束）。
        """
        self.valence += delta.valence * intensity
        self.arousal += delta.arousal * intensity
        self.dominance += delta.dominance * intensity

        delta_mag = math.sqrt(delta.valence**2 + delta.arousal**2 + delta.dominance**2)

        for dim_name in ("valence", "arousal", "dominance"):
            u_field = f"{dim_name}_uncertainty"
            delta_val = getattr(delta, dim_name)
            u = getattr(self, u_field)
            u *= 0.9  # 既存不確実性の緩やかな減衰（新情報による収束）
            u += delta.conflict * max(0.2, min(1.0, delta_mag)) * 0.3  # 葛藤→不確実性増
            u = max(0.0, u - (1.0 - delta.conflict) * abs(delta_val) * intensity * 0.15)  # 明確→減少
            setattr(self, u_field, max(0.0, min(1.0, u)))

        self._clamp()
        self.updated_at = time.time()

    def _clamp(self) -> None:
        self.valence = max(-1.0, min(1.0, self.valence))
        self.arousal = max(0.0, min(1.0, self.arousal))
        self.dominance = max(0.0, min(1.0, self.dominance))
        self.valence_uncertainty = max(0.0, min(1.0, self.valence_uncertainty))
        self.arousal_uncertainty = max(0.0, min(1.0, self.arousal_uncertainty))
        self.dominance_uncertainty = max(0.0, min(1.0, self.dominance_uncertainty))

    def to_dict(self) -> dict[str, float]:
        return {
            "valence": round(self.valence, 3),
            "arousal": round(self.arousal, 3),
            "dominance": round(self.dominance, 3),
            "valence_uncertainty": round(self.valence_uncertainty, 3),
            "arousal_uncertainty": round(self.arousal_uncertainty, 3),
            "dominance_uncertainty": round(self.dominance_uncertainty, 3),
        }

    @property
    def overall_uncertainty(self) -> float:
        """3次元の平均不確実性（全体の葛藤度）"""
        return (self.valence_uncertainty + self.arousal_uncertainty + self.dominance_uncertainty) / 3.0


@dataclass
class EmotionDelta:
    """扁桃体が出力する感情変化量（PAD + 葛藤度）。"""

    valence: float = 0.0
    arousal: float = 0.0
    dominance: float = 0.0
    conflict: float = 0.0  # [0, 1] 信号葛藤度。0=単一方向, 1=最大葛藤

    def scale(self, factor: float) -> EmotionDelta:
        return EmotionDelta(
            valence=self.valence * factor,
            arousal=self.arousal * factor,
            dominance=self.dominance * factor,
            conflict=self.conflict,  # 葛藤度はスケーリングしない（信号品質は不変）
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


@dataclass
class DriveState:
    """PSI理論等の認知アーキテクチャに基づく動機づけ（欲求）モデル。

    時間経過とともに自然蓄積し、行動（対話や検索など）によって解消される。

    Attributes:
        curiosity: 情報探索や思考の動機（不確実性の解消）。検索などで低下。
        social_need: ユーザーとの対話の動機（親和欲求）。発話で低下。
        maintenance: 記憶整理の動機（自己保全）。Reflexion等で低下。
    """

    curiosity: float = 0.0
    social_need: float = 0.0
    maintenance: float = 0.0
    updated_at: float = field(default_factory=time.time)

    def accumulate(self, dt: float | None = None) -> None:
        """時間経過による欲求の自然蓄積。"""
        if dt is None:
            now = time.time()
            dt = now - self.updated_at
            self.updated_at = now
        else:
            self.updated_at += dt

        if dt <= 0:
            return

        minutes = dt / 60.0
        # 各欲求の蓄積レート（1分あたり）
        rate_curiosity = 0.015
        rate_social = 0.01
        rate_maintenance = 0.005

        self.curiosity += rate_curiosity * minutes
        self.social_need += rate_social * minutes
        self.maintenance += rate_maintenance * minutes

        self._clamp()

    def satisfy(self, need_type: str, amount: float) -> None:
        """行動による欲求の解消（低下）。"""
        if need_type == "curiosity":
            self.curiosity -= amount
        elif need_type == "social_need":
            self.social_need -= amount
        elif need_type == "maintenance":
            self.maintenance -= amount
        self._clamp()

    def _clamp(self) -> None:
        self.curiosity = max(0.0, min(1.0, self.curiosity))
        self.social_need = max(0.0, min(1.0, self.social_need))
        self.maintenance = max(0.0, min(1.0, self.maintenance))

    def to_dict(self) -> dict[str, float]:
        return {
            "curiosity": round(self.curiosity, 3),
            "social_need": round(self.social_need, 3),
            "maintenance": round(self.maintenance, 3),
        }

    def get_dominant_needs(self) -> list[tuple[str, float]]:
        """最も欲求レベルの高いものから順に返す"""
        needs = [("curiosity", self.curiosity), ("social_need", self.social_need), ("maintenance", self.maintenance)]
        needs.sort(key=lambda x: x[1], reverse=True)
        return needs
