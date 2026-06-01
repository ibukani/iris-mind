"""LangMem が受け取るべき structured Pydantic スキーマ群。

これらは「候補」の構造だけを定義する。最終的な記憶の確定は PromotionPolicy が担う。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

PreferenceCategory = Literal[
    "communication",
    "technical",
    "creative",
    "personal_preference",
    "avoidance",
    "project",
]
PreferenceScope = Literal["account", "room", "global"]

StyleKind = Literal[
    "tone_preference",
    "successful_pattern",
    "running_gag",
    "avoidance_rule",
    "chaos_preference",
    "conversation_strategy",
]

RelationshipSignal = Literal[
    "trust_increase",
    "trust_decrease",
    "familiarity_increase",
    "boundary_set",
    "preference_disclosed",
    "repair_needed",
]

AppraisalDimension = Literal[
    "novelty",
    "pleasantness",
    "goal_relevance",
    "agency",
    "coping_potential",
    "accountability",
    "control",
    "social_norms",
]


class UserPreferenceMemory(BaseModel):
    """ユーザの好み/傾向候補。"""

    category: PreferenceCategory
    content: str
    evidence: str
    confidence: float = Field(ge=0.0, le=1.0)
    scope: PreferenceScope = "account"


class EpisodicInteractionMemory(BaseModel):
    """1 ターン分のインタラクション要約候補。"""

    situation: str
    user_intent: str
    assistant_action: str
    result: str
    lesson: str
    confidence: float = Field(ge=0.0, le=1.0)


class StyleMemory(BaseModel):
    """スタイル/手続き記憶の候補。"""

    kind: StyleKind
    content: str
    evidence: str
    confidence: float = Field(ge=0.0, le=1.0)
    activation_condition: str = ""


class RelationshipMemoryCandidate(BaseModel):
    """関係性に影響しそうなシグナル。"""

    signal: RelationshipSignal
    evidence: str
    suggested_delta: float = 0.0
    confidence: float = Field(ge=0.0, le=1.0)


class AppraisalMemoryCandidate(BaseModel):
    """appraisal 候補。あくまで参考値で Limbic ロジックを上書きしない。"""

    trigger_summary: str
    appraisal_dimension: AppraisalDimension
    estimated_delta: float = 0.0
    reason: str
    confidence: float = Field(ge=0.0, le=1.0)


class SemanticExtractionResult(BaseModel):
    """semantic 抽出パスは 0 個以上の UserPreferenceMemory を返す。"""

    items: list[UserPreferenceMemory] = Field(default_factory=list)


class EpisodicExtractionResult(BaseModel):
    items: list[EpisodicInteractionMemory] = Field(default_factory=list)


class StyleExtractionResult(BaseModel):
    items: list[StyleMemory] = Field(default_factory=list)


class RelationshipExtractionResult(BaseModel):
    items: list[RelationshipMemoryCandidate] = Field(default_factory=list)


class AppraisalExtractionResult(BaseModel):
    items: list[AppraisalMemoryCandidate] = Field(default_factory=list)


__all__ = [
    "AppraisalExtractionResult",
    "AppraisalMemoryCandidate",
    "EpisodicExtractionResult",
    "EpisodicInteractionMemory",
    "RelationshipExtractionResult",
    "RelationshipMemoryCandidate",
    "SemanticExtractionResult",
    "StyleExtractionResult",
    "StyleMemory",
    "UserPreferenceMemory",
]
