from __future__ import annotations

import math
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import numpy as np

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


class _EmbeddingScorer:
    """ONNX MiniLM 埋め込みによる感情スコアラー。

    Phase 2: キーワードでは捉えにくい意味的な感情を検出。
    8つの基本感情アンカーとのコサイン類似度でPAD deltaを出力。
    """

    def __init__(self) -> None:
        self._ef: Any = None
        self._anchors: dict[str, tuple[np.ndarray, EmotionDelta]] | None = None

    def _lazy_init(self) -> bool:
        if self._anchors is not None:
            return True
        try:
            from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2
            import numpy as np

            self._ef = ONNXMiniLM_L6_V2()
            anchor_texts = {
                "joy": "joyful happy delighted cheerful",
                "sadness": "sad depressed miserable gloomy",
                "anger": "angry furious irritated frustrated",
                "fear": "scared anxious fearful worried",
                "surprise": "surprised amazed shocked astonished",
                "trust": "trusting grateful appreciative thankful",
                "anticipation": "anticipating expecting looking forward",
                "calmness": "calm relaxed peaceful serene",
            }
            self._anchors = {}
            for name, text in anchor_texts.items():
                vec = self._ef([text])[0]
                norm = np.linalg.norm(vec)
                if norm > 0:
                    vec = vec / norm
                self._anchors[name] = (vec, BASIC_EMOTIONS[name])
            return True
        except Exception:
            logger.warning("EmbeddingScorer: ONNX model unavailable, falling back to keyword-only")
            self._anchors = {}
            return False

    def score(self, text: str) -> EmotionDelta:
        if not self._lazy_init() or not self._anchors:
            return EmotionDelta()

        import numpy as np

        vec = self._ef([text])[0]
        norm = np.linalg.norm(vec)
        if norm == 0:
            return EmotionDelta()
        vec = vec / norm

        total_v = total_a = total_d = 0.0
        total_w = 0.0
        for anchor, delta in self._anchors.values():
            sim = float(np.dot(vec, anchor))
            if sim > 0.25:
                w = sim - 0.25
                total_v += delta.valence * w
                total_a += delta.arousal * w
                total_d += delta.dominance * w
                total_w += w

        if total_w == 0:
            return EmotionDelta()

        return EmotionDelta(
            valence=max(-0.8, min(0.8, total_v / total_w * 0.8)),
            arousal=max(0.0, min(0.8, ((total_a / total_w + 1) / 2) * 0.8)),
            dominance=max(-0.6, min(0.6, total_d / total_w * 0.6)),
        )


class Amygdala:
    """扁桃体: 入力テキストの感情評価。

    Phase 1: キーワードベース（高速、軽量、LLM不要）
    Phase 2 (将来): LLMアシスト（高精度）

    脳科学:
        扁桃体は感覚入力の感情的な意義を素早く評価する。
        特に恐怖・報酬・社会的刺激に対して即時的な価値判断を行う。
    """

    def __init__(self, embedding_scorer: _EmbeddingScorer | None = None) -> None:
        self._positive = _KeywordCounter(_POSITIVE_WORDS)
        self._negative = _KeywordCounter(_NEGATIVE_WORDS)
        self._high_arousal = _KeywordCounter(_HIGH_AROUSAL_MARKERS)
        self._appreciation = _KeywordCounter(_APPRECIATION_WORDS)
        self._criticism = _KeywordCounter(_CRITICISM_WORDS)
        self._embedding_scorer = embedding_scorer or _EmbeddingScorer()

    def assess(self, text: str) -> EmotionDelta:
        if not text:
            return EmotionDelta()

        # 1. キーワード評価（常時実行、高速）
        keyword_delta = self._keyword_assess(text)

        # 2. 埋め込み評価（ONNX、意味ベース）
        embedding_delta = self._embedding_scorer.score(text)

        # 3. ハイブリッド統合
        kw_energy = abs(keyword_delta.valence) + keyword_delta.arousal
        emb_energy = abs(embedding_delta.valence) + embedding_delta.arousal

        if emb_energy == 0:
            return keyword_delta
        if kw_energy == 0:
            return embedding_delta

        kw_w = kw_energy / (kw_energy + emb_energy + 0.01)
        emb_w = 1.0 - kw_w

        return EmotionDelta(
            valence=keyword_delta.valence * kw_w + embedding_delta.valence * emb_w,
            arousal=keyword_delta.arousal * kw_w + embedding_delta.arousal * emb_w,
            dominance=keyword_delta.dominance * kw_w + embedding_delta.dominance * emb_w,
            conflict=max(keyword_delta.conflict, embedding_delta.conflict),
        )

    def _keyword_assess(self, text: str) -> EmotionDelta:
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

        total_valence = n_pos + n_neg
        conflict = 2.0 * min(n_pos, n_neg) / max(total_valence, 1) if total_valence > 0 else 0.0
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
