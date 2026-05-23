from __future__ import annotations

from collections.abc import Callable
from typing import TypedDict

from iris.limbic.models import EmotionState


class _MoodEntry(TypedDict):
    condition: Callable[[EmotionState], bool]
    text: str
    short: str


_MOOD_DESCRIPTIONS: list[_MoodEntry] = [
    {
        "condition": lambda e: e.valence > 0.5 and e.arousal > 0.4,
        "text": "わくわくした気分です！何か楽しいことがありそう。",
        "short": "わくわく",
    },
    {
        "condition": lambda e: e.valence > 0.3 and e.arousal < 0.3,
        "text": "穏やかな気分です。のんびり過ごせそうです。",
        "short": "穏やか",
    },
    {
        "condition": lambda e: e.valence > 0.3,
        "text": "良い気分です。今日は何か良いことがありそうです。",
        "short": "良い気分",
    },
    {
        "condition": lambda e: e.valence < -0.5 and e.arousal > 0.4,
        "text": "少しイライラしています。深呼吸が必要かもしれません。",
        "short": "イライラ",
    },
    {
        "condition": lambda e: e.valence < -0.3 and e.arousal < 0.3,
        "text": "少し沈んだ気分です。静かに過ごしたい気分です。",
        "short": "沈み気味",
    },
    {
        "condition": lambda e: e.valence < -0.3,
        "text": "あまり良い気分ではありません。何か気分転換が必要かもしれません。",
        "short": "不調",
    },
    {
        "condition": lambda e: e.arousal > 0.6,
        "text": "なんだか落ち着かない気分です。何かが起こりそう。",
        "short": "落ち着かない",
    },
    {
        "condition": lambda e: e.dominance > 0.5,
        "text": "自信にあふれています。何にでも挑戦できる気がします。",
        "short": "自信満々",
    },
    {
        "condition": lambda e: e.dominance < 0.3,
        "text": "少し自信がありません。慎重に行きたいです。",
        "short": "自信なし",
    },
]


class MoodEngine:
    """PAD 3次元感情状態 → 気分テキスト / 応答スタイル 変換。

    純粋関数の集まり。LimbicManager から分離して単一責任化。
    """

    @staticmethod
    def is_neutral(e: EmotionState) -> bool:
        return abs(e.valence) < 0.1 and e.arousal < 0.15 and abs(e.dominance - 0.5) < 0.1

    @staticmethod
    def describe_mood(e: EmotionState, style: str = "full") -> str:
        if MoodEngine.is_neutral(e):
            return ""
        for entry in _MOOD_DESCRIPTIONS:
            if entry["condition"](e):
                return entry["short"] if style == "short" else entry["text"]
        return ""

    @staticmethod
    def generate_response_style(e: EmotionState) -> str:
        if MoodEngine.is_neutral(e):
            return ""

        hints: list[str] = []
        MoodEngine._build_valence_hints(e, hints)
        MoodEngine._build_arousal_hints(e, hints)
        MoodEngine._build_dominance_hints(e, hints)

        if not hints:
            return ""

        return "## 応答スタイル\n" + "\n".join(f"- {h}" for h in hints)

    @staticmethod
    def _build_valence_hints(e: EmotionState, hints: list[str]) -> None:
        if e.valence > 0.5:
            hints.append("明るく温かいトーンで応答してください")
            if e.arousal > 0.4:
                hints.append(
                    "発話の冒頭や途中に、感情に合わせた感嘆詞（例：『やったー！』『わーい！』『やった！』）を自然に混ぜて、非常に嬉しそうに応答してください"
                )
            else:
                hints.append(
                    "発話の冒頭や途中に、穏やかな感嘆表現（例：『ふふっ』『そうだね』）を少し交えて嬉しそうに応答してください"
                )
        elif e.valence > 0.2:
            hints.append("穏やかで親しみやすいトーンで応答してください")
            hints.append("親しみやすく、優しい相槌や感嘆表現（例：『ふふっ』『そうだね』）を少し交えて応答してください")
        elif e.valence < -0.5:
            hints.append("簡潔に、1文以内の最小限の言葉で応答してください")
            if e.arousal > 0.4:
                hints.append(
                    "発話の冒頭や途中に、イライラを表す感嘆詞（例：『はぁ…』『もう！』）を交え、不機嫌でぶっきらぼうに応答してください"
                )
            else:
                hints.append(
                    "発話の冒頭や途中に、落胆を表す感嘆表現（例：『はぁ…』『ふぅ』）を交えて、冷淡に応答してください"
                )
        elif e.valence < -0.2:
            hints.append("やや控えめに、1文程度の短い言葉で応答してください")
            hints.append(
                "発話の冒頭や途中に、元気がなさそうな感嘆詞（例：『うう…』『え〜ん』『しゅん…』）を自然に交え、悲しそうに応答してください"
            )

    @staticmethod
    def _build_arousal_hints(e: EmotionState, hints: list[str]) -> None:
        if e.arousal > 0.6:
            hints.append("テンポ良く、1〜2文の短い言葉で活発に応答してください")
            hints.append("焦りや興奮を言葉の端々に表し、感嘆符『！』を多めに使ってテンポ良く応答してください")
        elif e.arousal < 0.2:
            hints.append("ゆったりとしたペースで、1〜2文程度で応答してください")

    @staticmethod
    def _build_dominance_hints(e: EmotionState, hints: list[str]) -> None:
        if e.dominance > 0.6:
            hints.append("自信を持って明確に応答してください")
        elif e.dominance < 0.3:
            hints.append("慎重に、確認しながら応答してください")
