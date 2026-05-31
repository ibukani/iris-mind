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
    """Bowlby attachment theory ベースの関係性管理 (per-account)"""

    _GLOBAL_KEY = "__global__"

    def __init__(self) -> None:
        self._states: dict[str, RelationshipState] = {}

    def _get_state(self, account_id: str) -> RelationshipState:
        key = account_id or self._GLOBAL_KEY
        if key not in self._states:
            self._states[key] = RelationshipState()
        return self._states[key]

    def update(
        self,
        emotion: CompanionEmotion,
        account_id: str = "",
        context_type: str | None = None,
        user_profile: dict[str, Any] | None = None,
    ) -> RelationshipState:
        """感情と文脈に基づいて関係性状態を更新 (per-account)"""
        state = self._get_state(account_id)
        impact = _EMOTION_RELATIONSHIP_IMPACT.get(emotion.primary, {})
        state.trust = max(0.0, min(1.0, state.trust + impact.get("trust", 0.0)))
        state.familiarity = max(0.0, min(1.0, state.familiarity + impact.get("familiarity", 0.0)))

        if context_type and context_type in _DISCLOSURE_PATTERNS:
            disclosure = _DISCLOSURE_PATTERNS[context_type]
            state.disclosure_depth = max(0.0, min(1.0, state.disclosure_depth + disclosure))

        state.interaction_count += 1
        self._update_level(state)
        self._update_attachment_style(state, user_profile)

        logger.debug(
            "Relationship updated: account={} level={} trust={:.2f} familiarity={:.2f}",
            account_id or "(global)",
            state.level.name,
            state.trust,
            state.familiarity,
        )

        return replace(state)

    def get_state(self, account_id: str = "") -> RelationshipState:
        return replace(self._get_state(account_id))

    def get_all_states(self) -> dict[str, RelationshipState]:
        return {k: replace(v) for k, v in self._states.items()}

    def _update_level(self, state: RelationshipState) -> None:
        if state.trust >= _TRUST_THRESHOLDS[RelationshipLevel.FAMILIAR]:
            if state.level < RelationshipLevel.BONDED:
                state.level = RelationshipLevel.BONDED
                logger.info("Relationship level: → BONDED")
        elif (
            state.trust >= _TRUST_THRESHOLDS[RelationshipLevel.ACQUAINTANCE]
            and state.level < RelationshipLevel.FAMILIAR
        ):
            state.level = RelationshipLevel.FAMILIAR
            logger.info("Relationship level: → FAMILIAR")

    def _update_attachment_style(
        self,
        state: RelationshipState,
        user_profile: dict[str, Any] | None = None,
    ) -> None:
        if user_profile and "attachment_style" in user_profile:
            with contextlib.suppress(ValueError):
                state.attachment_style = AttachmentStyle(user_profile["attachment_style"])

    def get_profile(self, account_id: str = "") -> dict[str, Any]:
        """Appraisal用のユーザープロフィールを返す (per-account)"""
        state = self._get_state(account_id)
        return {
            "trust_level": state.trust,
            "familiarity": state.familiarity,
            "relationship_level": state.level.value,
            "attachment_style": state.attachment_style.value,
            "disclosure_depth": state.disclosure_depth,
        }
