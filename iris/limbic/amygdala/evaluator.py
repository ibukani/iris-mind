from __future__ import annotations

import math
import re

from loguru import logger

from iris.limbic.models import BASIC_EMOTIONS, EmotionDelta

_POSITIVE_WORDS: frozenset[str] = frozenset(
    {
        "ありがとう",
        "嬉しい",
        "楽しい",
        "素晴らしい",
        "最高",
        "好き",
        "いいね",
        "すごい",
        "素敵",
        "感動",
        "幸せ",
        "感謝",
        "助かる",
        "面白い",
        "笑",
        "w",
        "すげえ",
        "やった",
        "さすが",
        "thank",
        "love",
        "great",
        "awesome",
        "amazing",
        "wonderful",
        "happy",
        "excellent",
        "perfect",
        "beautiful",
        "nice",
    }
)

_NEGATIVE_WORDS: frozenset[str] = frozenset(
    {
        "残念",
        "つまらない",
        "ひどい",
        "悲しい",
        "最悪",
        "嫌い",
        "むかつく",
        "腹立つ",
        "イライラ",
        "疲れた",
        "つらい",
        "苦しい",
        "意味ない",
        "もういい",
        "ダメ",
        "無理",
        "死",
        "殺す",
        "hate",
        "terrible",
        "awful",
        "horrible",
        "bad",
        "worst",
        "sad",
        "angry",
        "bored",
        "tired",
        "useless",
    }
)

_HIGH_AROUSAL_MARKERS: frozenset[str] = frozenset(
    {
        "!",
        "？",
        "！",
        "本当",
        "まじ",
        "めっちゃ",
        "超",
        "やば",
        "マジ",
        "w",
        "笑",
        "www",
        "は？",
    }
)

_APPRECIATION_WORDS: frozenset[str] = frozenset(
    {
        "ありがとう",
        "感謝",
        "助かる",
        "thank",
        "thanks",
        "good",
    }
)

_CRITICISM_WORDS: frozenset[str] = frozenset(
    {
        "違う",
        "間違い",
        "バカ",
        "アホ",
        "無能",
        "使えない",
        "wrong",
        "incorrect",
        "stupid",
        "useless",
    }
)

_AGENTIVE_PATTERNS: list[tuple[re.Pattern, float]] = [
    (re.compile(r"\b(私|俺|僕|私が|自分は)\s*(が|は|を)"), 0.3),
    (re.compile(r"\b(I|I\'ll|I\'m|let me|my)\b"), 0.2),
    (re.compile(r"^(やって|して|実行|作っ|書い)"), 0.2),
    (re.compile(r"(決めた|決めたい|やる|やろう)"), 0.3),
]

_PASSIVE_PATTERNS: list[tuple[re.Pattern, float]] = [
    (re.compile(r"(させられる|されてる|やられ)"), -0.3),
    (re.compile(r"(わからない|できない|無理|難しい)"), -0.2),
    (re.compile(r"\b(can\'t|cannot|couldn\'t)\b"), -0.2),
]


class _KeywordCounter:
    def __init__(self, words: frozenset[str]) -> None:
        self._words = words

    def count(self, text: str) -> int:
        return sum(1 for w in self._words if w in text)


class Amygdala:
    """扁桃体: 入力テキストの感情評価。

    Phase 1: キーワードベース（高速、軽量、LLM不要）
    Phase 2 (将来): LLMアシスト（高精度）

    脳科学:
       扁桃体は感覚入力の感情的な意義を素早く評価する。
       特に恐怖・報酬・社会的刺激に対して即時的な価値判断を行う。
    """

    def __init__(self) -> None:
        self._positive = _KeywordCounter(_POSITIVE_WORDS)
        self._negative = _KeywordCounter(_NEGATIVE_WORDS)
        self._high_arousal = _KeywordCounter(_HIGH_AROUSAL_MARKERS)
        self._appreciation = _KeywordCounter(_APPRECIATION_WORDS)
        self._criticism = _KeywordCounter(_CRITICISM_WORDS)

    def assess(self, text: str) -> EmotionDelta:
        if not text:
            return EmotionDelta()

        lower = text.lower()
        n_pos = self._positive.count(lower)
        n_neg = self._negative.count(lower)
        n_arousal = self._high_arousal.count(text)
        n_appreciation = self._appreciation.count(lower)
        n_criticism = self._criticism.count(lower)

        if n_pos > 2 or n_neg > 2:
            logger.info("Amygdala: significant emotional input (pos=%d neg=%d arousal=%d)", n_pos, n_neg, n_arousal)

        if n_pos == 0 and n_neg == 0 and n_arousal == 0:
            return EmotionDelta()

        valence_raw = (n_pos - n_neg) / max(n_pos + n_neg, 1)
        arousal_raw = min(n_arousal / 3.0, 1.0)

        if len(text) < 10:
            arousal_raw *= 0.5

        if n_appreciation > 0:
            valence_raw += 0.3
        if n_criticism > 0:
            valence_raw -= 0.4

        dominance_score = self._estimate_dominance(text)

        # 葛藤度: 正と負のキーワードが同時に存在するほど高い
        total_valence = n_pos + n_neg
        conflict = 2.0 * min(n_pos, n_neg) / max(total_valence, 1) if total_valence > 0 else 0.0
        # 賞賛と批判の同時存在も葛藤に加算
        if n_appreciation > 0 and n_criticism > 0:
            conflict = max(conflict, 0.5)

        return EmotionDelta(
            valence=max(-1.0, min(1.0, valence_raw)) * 0.8,
            arousal=max(0.0, min(1.0, arousal_raw)) * 0.8,
            dominance=max(-1.0, min(1.0, dominance_score)) * 0.6,
            conflict=min(1.0, conflict),
        )

    def classify_emotion(self, text: str) -> str | None:
        delta = self.assess(text)
        if delta.valence == 0 and delta.arousal == 0:
            return None
        return min(
            BASIC_EMOTIONS.keys(),
            key=lambda name: _emotion_distance(delta, BASIC_EMOTIONS[name]),
        )

    @staticmethod
    def _estimate_dominance(text: str) -> float:
        score = 0.0
        for pat, val in _AGENTIVE_PATTERNS:
            if pat.search(text):
                score += val
        for pat, val in _PASSIVE_PATTERNS:
            if pat.search(text):
                score += val
        return max(-1.0, min(1.0, score))


def _emotion_distance(a: EmotionDelta, b: EmotionDelta) -> float:
    """ユークリッド距離にコサインペナルティを乗算したハイブリッド距離。"""
    dv = a.valence - b.valence
    da = a.arousal - b.arousal
    dd = a.dominance - b.dominance
    euclidean = math.sqrt(dv * dv + da * da + dd * dd)

    dot = a.valence * b.valence + a.arousal * b.arousal + a.dominance * b.dominance
    na = math.sqrt(a.valence**2 + a.arousal**2 + a.dominance**2)
    nb = math.sqrt(b.valence**2 + b.arousal**2 + b.dominance**2)
    cosine_sim = dot / (na * nb) if na * nb > 0 else 0.0

    return euclidean * (2.0 - cosine_sim)
