from __future__ import annotations

import re
from typing import Any

from .lexicon import CONTEXT_PATTERNS, KEYWORD_MAP, EmotionClassifierProtocol
from .models import (
    AppraisalDimensions,
    PrimaryAppraisal,
    SecondaryAppraisal,
)


class Appraiser:
    """2段階Appraisal (Lazarus: Primary + Secondary)

    責務:
    - 第一次評価: novelty / pleasantness / goal_relevance / agency / coping_potential
    - 第二次評価: accountability / control / controllability / social_norms
    - CAPE 6次元 (AppraisalDimensions) の算出
    """

    def __init__(self, emotion_classifier: EmotionClassifierProtocol | None = None) -> None:
        self._emotion_classifier = emotion_classifier
        self._keyword_compiled: dict[str, list[re.Pattern[str]]] = {
            emotion: [re.compile(re.escape(kw)) for kw in keywords] for emotion, keywords in KEYWORD_MAP.items()
        }
        self._context_compiled: dict[str, list[re.Pattern[str]]] = {
            ctx: [re.compile(p) for p in patterns] for ctx, patterns in CONTEXT_PATTERNS.items()
        }

    def appraise_primary(
        self,
        text: str,
        context: dict[str, Any] | None = None,
    ) -> PrimaryAppraisal:
        """第一次評価: Eventの個人的意味づけ"""
        ctx = context or {}
        word_emotions = self.detect_word_emotions(text)
        context_type = self.detect_context_type(text)

        novelty = self._score_novelty(ctx)
        pleasantness = self._score_pleasantness(word_emotions)
        goal_relevance = self._score_goal_relevance(context_type, ctx)
        agency = self._score_agency(ctx)
        coping_potential = self._score_coping_potential(ctx)

        return PrimaryAppraisal(
            novelty=novelty,
            pleasantness=pleasantness,
            goal_relevance=goal_relevance,
            agency=agency,
            coping_potential=coping_potential,
        )

    def appraise_secondary(
        self,
        primary: PrimaryAppraisal,
        user_profile: dict[str, Any] | None = None,
    ) -> SecondaryAppraisal:
        """第二次評価: 自己の対処能力評価"""
        profile = user_profile or {}
        trust_level = profile.get("trust_level", 0.5)
        familiarity = profile.get("familiarity", 0.0)

        accountability = min(1.0, trust_level * 0.7 + familiarity * 0.3)
        control = primary.coping_potential * 0.6 + trust_level * 0.4
        controllability = primary.coping_potential * 0.8 + familiarity * 0.2
        social_norms = 0.5 + familiarity * 0.3 + trust_level * 0.2

        return SecondaryAppraisal(
            accountability=accountability,
            control=control,
            controllability=controllability,
            social_norms=social_norms,
        )

    def compute_dimensions(
        self,
        primary: PrimaryAppraisal,
        secondary: SecondaryAppraisal,
    ) -> AppraisalDimensions:
        """Appraisal次元を計算 (CAPE 6次元)"""
        unpleasantness = max(0.0, -primary.pleasantness)
        control = secondary.control
        responsibility = secondary.accountability
        certainty = 1.0 - primary.novelty
        effort = 1.0 - primary.coping_potential
        attention = primary.goal_relevance

        return AppraisalDimensions(
            unpleasantness=unpleasantness,
            control=control,
            responsibility=responsibility,
            certainty=certainty,
            effort=effort,
            attention=attention,
        )

    # ---- ヘルパー ----

    def detect_word_emotions(self, text: str) -> dict[str, float]:
        if self._emotion_classifier is not None:
            return self._emotion_classifier.classify(text)
        return self._keyword_match(text)

    def _keyword_match(self, text: str) -> dict[str, float]:
        scores: dict[str, float] = {}
        for emotion, patterns in self._keyword_compiled.items():
            count = sum(1 for p in patterns if p.search(text))
            if count > 0:
                scores[emotion] = min(1.0, count * 0.3)
        return scores

    def detect_context_type(self, text: str) -> str | None:
        best_ctx: str | None = None
        best_count = 0
        for ctx, patterns in self._context_compiled.items():
            count = sum(1 for p in patterns if p.search(text))
            if count > best_count:
                best_count = count
                best_ctx = ctx
        return best_ctx

    def _score_novelty(self, ctx: dict[str, Any]) -> float:
        if ctx.get("is_new_topic", False):
            return 0.8
        if ctx.get("topic_changed", False):
            return 0.6
        return 0.3

    def _score_pleasantness(self, word_emotions: dict[str, float]) -> float:
        positive = sum(word_emotions.get(e, 0.0) for e in ("joy", "trust", "anticipation"))
        negative = sum(word_emotions.get(e, 0.0) for e in ("sadness", "anger", "fear", "disgust"))
        return max(-1.0, min(1.0, positive - negative))

    def _score_goal_relevance(self, context_type: str | None, ctx: dict[str, Any]) -> float:
        relevance_map = {
            "support_seeking": 0.9,
            "self_disclosure": 0.7,
            "positive_feedback": 0.4,
            "negative_feedback": 0.6,
        }
        if context_type and context_type in relevance_map:
            return relevance_map[context_type]
        if ctx.get("is_direct_question", False):
            return 0.8
        return 0.5

    def _score_agency(self, ctx: dict[str, Any]) -> float:
        if ctx.get("user_is_agent", False):
            return 0.8
        return 0.3

    def _score_coping_potential(self, ctx: dict[str, Any]) -> float:
        trust = float(ctx.get("trust_level", 0.5))
        familiarity = float(ctx.get("familiarity", 0.0))
        return min(1.0, trust * 0.6 + familiarity * 0.4)


__all__ = ["Appraiser"]
