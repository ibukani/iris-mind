from __future__ import annotations

import re

POSITIVE_WORDS: frozenset[str] = frozenset(
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

NEGATIVE_WORDS: frozenset[str] = frozenset(
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

HIGH_AROUSAL_MARKERS: frozenset[str] = frozenset(
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

APPRECIATION_WORDS: frozenset[str] = frozenset(
    {
        "ありがとう",
        "感謝",
        "助かる",
        "thank",
        "thanks",
        "good",
    }
)

CRITICISM_WORDS: frozenset[str] = frozenset(
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

AGENTIVE_PATTERNS: list[tuple[re.Pattern, float]] = [
    (re.compile(r"\b(私|俺|僕|私が|自分は)\s*(が|は|を)"), 0.3),
    (re.compile(r"\b(I|I\'ll|I\'m|let me|my)\b"), 0.2),
    (re.compile(r"^(やって|して|実行|作っ|書い)"), 0.2),
    (re.compile(r"(決めた|決めたい|やる|やろう)"), 0.3),
]

PASSIVE_PATTERNS: list[tuple[re.Pattern, float]] = [
    (re.compile(r"(させられる|されてる|やられ)"), -0.3),
    (re.compile(r"(わからない|できない|無理|難しい)"), -0.2),
    (re.compile(r"\b(can\'t|cannot|couldn\'t)\b"), -0.2),
]
