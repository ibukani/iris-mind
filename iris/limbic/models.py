from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, IntEnum
from typing import Any

# ---- Appraisal 次元 ----


@dataclass
class PrimaryAppraisal:
    """Lazarusの第一次評価: Eventの個人的意味づけ"""

    novelty: float = 0.0
    pleasantness: float = 0.0
    goal_relevance: float = 0.0
    agency: float = 0.0
    coping_potential: float = 0.0


@dataclass
class SecondaryAppraisal:
    """Lazarusの第二次評価: 自己の対処能力評価"""

    accountability: float = 0.0
    control: float = 0.0
    controllability: float = 0.0
    social_norms: float = 0.0


@dataclass
class AppraisalDimensions:
    """CAPE framework の 6 次元 (unpleasantness, control, responsibility, certainty, effort, attention)"""

    unpleasantness: float = 0.0
    control: float = 0.0
    responsibility: float = 0.0
    certainty: float = 0.0
    effort: float = 0.0
    attention: float = 0.0


# ---- Plutchik 8 基本感情 ----


class PlutchikEmotion(Enum):
    JOY = "joy"
    SADNESS = "sadness"
    ANTICIPATION = "anticipation"
    SURPRISE = "surprise"
    ANGER = "anger"
    FEAR = "fear"
    DISGUST = "disgust"
    TRUST = "trust"


PLUTCHIK_VAD: dict[PlutchikEmotion, tuple[float, float, float]] = {
    PlutchikEmotion.JOY: (0.8, 0.6, 0.6),
    PlutchikEmotion.SADNESS: (-0.6, -0.4, -0.3),
    PlutchikEmotion.ANTICIPATION: (0.4, 0.7, 0.3),
    PlutchikEmotion.SURPRISE: (0.2, 0.9, -0.2),
    PlutchikEmotion.ANGER: (-0.7, 0.8, 0.5),
    PlutchikEmotion.FEAR: (-0.7, 0.8, -0.6),
    PlutchikEmotion.DISGUST: (-0.6, 0.3, 0.1),
    PlutchikEmotion.TRUST: (0.5, 0.2, 0.3),
}


@dataclass
class CompanionEmotion:
    """コンパニオンの感情状態 (Plutchik + VAD)"""

    primary: PlutchikEmotion = PlutchikEmotion.JOY
    intensity: float = 0.0
    valence: float = 0.0
    arousal: float = 0.0
    dominance: float = 0.0
    secondary: PlutchikEmotion | None = None
    secondary_intensity: float = 0.0

    def to_vad_dict(self) -> dict[str, float]:
        return {"valence": self.valence, "arousal": self.arousal, "dominance": self.dominance}

    def to_dict(self) -> dict[str, Any]:
        return {
            "primary": self.primary.value,
            "intensity": self.intensity,
            "valence": self.valence,
            "arousal": self.arousal,
            "dominance": self.dominance,
            "secondary": self.secondary.value if self.secondary else None,
            "secondary_intensity": self.secondary_intensity,
        }


# ---- Mood dynamics ----


@dataclass
class Mood:
    """slow-moving baseline (時間減衰あり)"""

    valence: float = 0.0
    arousal: float = 0.0
    dominance: float = 0.0
    last_updated: float = 0.0

    def to_dict(self) -> dict[str, float]:
        return {"valence": self.valence, "arousal": self.arousal, "dominance": self.dominance}


# ---- 関係性 ----


class RelationshipLevel(IntEnum):
    ACQUAINTANCE = 0
    FAMILIAR = 1
    BONDED = 2


class AttachmentStyle(Enum):
    SECURE = "secure"
    ANXIOUS = "anxious"
    AVOIDANT = "avoidant"
    DISORGANIZED = "disorganized"


@dataclass
class RelationshipState:
    """Bowlby attachment theory ベースの関係性状態"""

    level: RelationshipLevel = RelationshipLevel.ACQUAINTANCE
    trust: float = 0.1
    familiarity: float = 0.0
    attachment_style: AttachmentStyle = AttachmentStyle.SECURE
    interaction_count: int = 0
    disclosure_depth: float = 0.0
    history: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "level": self.level.name,
            "trust": self.trust,
            "familiarity": self.familiarity,
            "attachment_style": self.attachment_style.value,
            "interaction_count": self.interaction_count,
            "disclosure_depth": self.disclosure_depth,
        }


# ---- 結果型 ----


@dataclass
class EmotionResult:
    """Appraisal → Emotion → Relationship パイプラインの出力"""

    appraisal: AppraisalDimensions
    emotion: CompanionEmotion
    mood: Mood
    relationship: RelationshipState
    reappraisal_needed: bool = False
    reappraisal_suggestion: str = ""
