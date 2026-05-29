from __future__ import annotations

import contextlib
from dataclasses import replace
from typing import Any

from loguru import logger

from .models import (
    AttachmentStyle,
    CompanionEmotion,
    PlutchikEmotion,
    RelationshipLevel,
    RelationshipState,
)

# 関係性段階の閾値
_TRUST_THRESHOLDS = {
    RelationshipLevel.ACQUAINTANCE: 0.3,
    RelationshipLevel.FAMILIAR: 0.7,
    RelationshipLevel.BONDED: float("inf"),
}

# 感情タイプ → 関係性影響
_EMOTION_RELATIONSHIP_IMPACT: dict[PlutchikEmotion, dict[str, float]] = {
    PlutchikEmotion.JOY: {"trust": 0.02, "familiarity": 0.03},
    PlutchikEmotion.TRUST: {"trust": 0.04, "familiarity": 0.02},
    PlutchikEmotion.SADNESS: {"trust": -0.01, "familiarity": 0.01},
    PlutchikEmotion.ANGER: {"trust": -0.03, "familiarity": -0.01},
    PlutchikEmotion.FEAR: {"trust": -0.02, "familiarity": 0.0},
    PlutchikEmotion.DISGUST: {"trust": -0.04, "familiarity": -0.02},
    PlutchikEmotion.ANTICIPATION: {"trust": 0.01, "familiarity": 0.02},
    PlutchikEmotion.SURPRISE: {"trust": 0.0, "familiarity": 0.01},
}

# 自己開示パターン
_DISCLOSURE_PATTERNS: dict[str, float] = {
    "self_disclosure": 0.15,
    "support_seeking": 0.10,
    "positive_feedback": 0.05,
    "negative_feedback": 0.03,
}


class RelationshipManager:
    """Bowlby attachment theory ベースの関係性管理"""

    def __init__(self) -> None:
        self._state = RelationshipState()

    def update(
        self,
        emotion: CompanionEmotion,
        context_type: str | None = None,
        user_profile: dict[str, Any] | None = None,
    ) -> RelationshipState:
        """感情と文脈に基づいて関係性状態を更新"""
        impact = _EMOTION_RELATIONSHIP_IMPACT.get(emotion.primary, {})
        self._state.trust = max(0.0, min(1.0, self._state.trust + impact.get("trust", 0.0)))
        self._state.familiarity = max(0.0, min(1.0, self._state.familiarity + impact.get("familiarity", 0.0)))

        if context_type and context_type in _DISCLOSURE_PATTERNS:
            disclosure = _DISCLOSURE_PATTERNS[context_type]
            self._state.disclosure_depth = max(0.0, min(1.0, self._state.disclosure_depth + disclosure))

        self._state.interaction_count += 1
        self._update_level()
        self._update_attachment_style(user_profile)

        logger.debug(
            "Relationship updated: level={} trust={:.2f} familiarity={:.2f}",
            self._state.level.name,
            self._state.trust,
            self._state.familiarity,
        )

        return replace(self._state)

    def get_state(self) -> RelationshipState:
        return replace(self._state)

    def _update_level(self) -> None:
        if self._state.trust >= _TRUST_THRESHOLDS[RelationshipLevel.FAMILIAR]:
            if self._state.level < RelationshipLevel.BONDED:
                self._state.level = RelationshipLevel.BONDED
                logger.info("Relationship level: → BONDED")
        elif (
            self._state.trust >= _TRUST_THRESHOLDS[RelationshipLevel.ACQUAINTANCE]
            and self._state.level < RelationshipLevel.FAMILIAR
        ):
            self._state.level = RelationshipLevel.FAMILIAR
            logger.info("Relationship level: → FAMILIAR")

    def _update_attachment_style(self, user_profile: dict[str, Any] | None = None) -> None:
        if user_profile and "attachment_style" in user_profile:
            with contextlib.suppress(ValueError):
                self._state.attachment_style = AttachmentStyle(user_profile["attachment_style"])

    def get_profile(self) -> dict[str, Any]:
        """Appraisal用のユーザープロフィールを返す"""
        return {
            "trust_level": self._state.trust,
            "familiarity": self._state.familiarity,
            "relationship_level": self._state.level.value,
            "attachment_style": self._state.attachment_style.value,
            "disclosure_depth": self._state.disclosure_depth,
        }
