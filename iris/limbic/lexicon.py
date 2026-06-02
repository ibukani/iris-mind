"""感情 / 文脈パターン辞書 (lexicon)。

Plutchik 8感情のキーワードマップと、self_disclosure / support_seeking 等の
文脈パターン（regex）を保持する。Appraiser はこの辞書を使って
keyword ベース分類と文脈検出を行う。

拡張ポイント:
- LLM ベースの `EmotionClassifierProtocol` を Appraiser に注入すると
  keyword マッチより高精度な分類を利用できる。
"""

from __future__ import annotations

from typing import Protocol

# 感情キーワード辞書 (Plutchik 8感情)
KEYWORD_MAP: dict[str, list[str]] = {
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
CONTEXT_PATTERNS: dict[str, list[str]] = {
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


class EmotionClassifierProtocol(Protocol):
    """感情分類器の Protocol。LLM ベースの実装に差し替え可能。"""

    def classify(self, text: str) -> dict[str, float]:
        """text を入力に取り、{emotion: score} の dict を返す。"""
        ...


__all__ = ["CONTEXT_PATTERNS", "KEYWORD_MAP", "EmotionClassifierProtocol"]
