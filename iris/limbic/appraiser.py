from __future__ import annotations

import re
from typing import Any

from .models import (
    AppraisalDimensions,
    PrimaryAppraisal,
    SecondaryAppraisal,
)

# 感情キーワード辞書 (Plutchik 8感情)
_KEYWORD_MAP: dict[str, list[str]] = {
    "joy": [
        "嬉しい",
        "楽しい",
        "幸せ",
        "うれしい",
        "たのしい",
        "わくわく",
        "良かった",
        "やった",
        "最高",
        "素晴らしい",
        "良い",
    ],
    "sadness": [
        "悲しい",
        "残念",
        "寂しい",
        "つらい",
        "辛い",
        "落ち込む",
        "淋しい",
        "虚しい",
        "悔しい",
        "惜しい",
    ],
    "anticipation": [
        "楽しみ",
        "期待",
        "待っている",
        "欲しい",
        "いつか",
        "これから",
        "将来",
        "未来",
        "予定",
        "計画",
    ],
    "surprise": [
        "驚いた",
        "びっくり",
        "まさか",
        "信じられない",
        "すごい",
        "驚き",
        "意外",
        "想定外",
        "予期せぬ",
    ],
    "anger": [
        "腹が立つ",
        "腹立つ",
        "怒り",
        "イライラ",
        "むかつく",
        "許せない",
        "ひどい",
        "最悪",
        "怒る",
        "怒らせる",
    ],
    "fear": [
        "怖い",
        "恐い",
        "不安",
        "心配",
        "おびえる",
        "怯える",
        "危ない",
        "リスク",
        "恐怖",
    ],
    "disgust": [
        "嫌い",
        "気持ち悪い",
        "不快",
        "うんざり",
        "嫌",
        "嫌悪",
        "吐き気",
    ],
    "trust": [
        "信頼",
        "頼れる",
        "安心",
        "大丈夫",
        "信じる",
        "任せる",
        "頼もしい",
    ],
}

# 文脈パターン (regex)
_CONTEXT_PATTERNS: dict[str, list[str]] = {
    "self_disclosure": [
        r"私[はが].*思う",
        r"私の.*経験",
        r"実は.*",
        r"正直.*",
        r"隠し事.*",
    ],
    "support_seeking": [
        r"助けて",
        r"相談.*",
        r"困[っり]た",
        r"どうしよ",
        r"アドバイス",
    ],
    "positive_feedback": [
        r"ありがとう",
        r"助かった",
        r"良い.*感じ",
        r"満足",
        r"嬉しい",
    ],
    "negative_feedback": [
        r"悪い.*感じ",
        r"不満",
        r"がっかり",
        r"期待外れ",
        r"ひどい",
    ],
}


class Appraiser:
    """2段階Appraisal (Lazarus: Primary + Secondary)"""

    def __init__(self) -> None:
        self._keyword_compiled: dict[str, list[re.Pattern[str]]] = {}
        for emotion, keywords in _KEYWORD_MAP.items():
            self._keyword_compiled[emotion] = [re.compile(re.escape(kw)) for kw in keywords]
        self._context_compiled: dict[str, list[re.Pattern[str]]] = {}
        for ctx, patterns in _CONTEXT_PATTERNS.items():
            self._context_compiled[ctx] = [re.compile(p) for p in patterns]

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
