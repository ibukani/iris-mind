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

    量子認知拡張:
      - 不確実性（重ね合わせ）→ 気分表現の変調 / 応答スタイルの鈍化
      - 文脈依存崩壊（測定問題）→ 会話文脈によって同じPADから異なる応答スタイル
    """

    UNCERTAINTY_THRESHOLD = 0.4  # この閾値を超えると不確実性が出力に影響

    @staticmethod
    def is_neutral(e: EmotionState) -> bool:
        """中立判定: PAD値 + 不確実性も考慮。

        不確実性が高い状態は「機能的に中立」と見なす（出力を抑制）。
        """
        pad_neutral = abs(e.valence) < 0.1 and e.arousal < 0.15 and abs(e.dominance - 0.5) < 0.1
        high_uncertainty = e.overall_uncertainty > 0.6
        return pad_neutral or high_uncertainty

    @staticmethod
    def describe_mood(e: EmotionState, style: str = "full") -> str:
        if MoodEngine.is_neutral(e):
            return ""
        base = ""
        for entry in _MOOD_DESCRIPTIONS:
            if entry["condition"](e):
                base = entry["short"] if style == "short" else entry["text"]
                break
        if not base:
            return ""
        # 不確実性が中程度なら葛藤ニュアンスを追加
        u = e.overall_uncertainty
        if u > 0.3:
            base += "（でも、ちょっと複雑な気持ちも…）" if style == "full" else "･･･"
        return base

    @staticmethod
    def generate_response_style(e: EmotionState, context: str = "") -> str:
        if MoodEngine.is_neutral(e):
            return ""

        # 不確実性による実効PADの崩壊（重ね合わせ→実数値への射影）
        eff_v = e.valence * (1.0 - e.valence_uncertainty)
        eff_a = e.arousal * (1.0 - e.arousal_uncertainty)
        eff_d = e.dominance * (1.0 - e.dominance_uncertainty)

        # 不確実性が高い → 控えめなトーンにフォールバック
        if e.overall_uncertainty > MoodEngine.UNCERTAINTY_THRESHOLD:
            hints = MoodEngine._build_uncertain_hints(e)
        else:
            hints = MoodEngine._build_hints(eff_v, eff_a, eff_d)

        # 文脈依存崩壊: 会話文脈で最終調整
        MoodEngine._apply_context_collapse(hints, context)

        if not hints:
            return ""

        return "## 応答スタイル\n" + "\n".join(f"- {h}" for h in hints)

    @staticmethod
    def _build_hints(v: float, a: float, d: float) -> list[str]:
        """実効PAD値から応答ヒントを構築（不確実性崩壊後）。"""
        hints: list[str] = []
        MoodEngine._build_valence_hints(v, a, hints)
        MoodEngine._build_arousal_hints(a, hints)
        MoodEngine._build_dominance_hints(d, hints)
        return hints

    @staticmethod
    def _build_uncertain_hints(e: EmotionState) -> list[str]:
        """不確実性が高い場合の控えめ応答スタイル。"""
        hints: list[str] = []
        if e.overall_uncertainty > 0.6:
            hints.append("控えめに、短い言葉で応答してください")
            hints.append("迷いや葛藤を感じさせる口調で、断定を避けて応答してください")
        else:
            hints.append("やや控えめに、断定を避けつつ自然に応答してください")
        return hints

    @staticmethod
    def _apply_context_collapse(hints: list[str], context: str) -> None:
        """文脈依存崩壊: 会話文脈によって測定結果（応答スタイル）が変わる。"""
        if not hints or not context:
            return
        if "task" in context or "命令" in context or "依頼" in context:
            # タスク文脈 → 感情抑制
            hints.insert(0, "簡潔に、タスク遂行を最優先して応答してください")
        elif "chat" in context or "相談" in context or "雑談" in context:
            # 親密文脈 → 感情強調
            hints.insert(0, "共感を示し、温かみのある口調で応答してください")

    @staticmethod
    def _build_valence_hints(v: float, a: float, hints: list[str]) -> None:
        if v > 0.5:
            hints.append("明るく温かいトーンで応答してください")
            if a > 0.4:
                hints.append(
                    "発話の冒頭や途中に、感情に合わせた感嘆詞（例：『やったー！』『わーい！』『やった！』）を自然に混ぜて、非常に嬉しそうに応答してください"
                )
            else:
                hints.append(
                    "発話の冒頭や途中に、穏やかな感嘆表現（例：『ふふっ』『そうだね』）を少し交えて嬉しそうに応答してください"
                )
        elif v > 0.2:
            hints.append("穏やかで親しみやすいトーンで応答してください")
            hints.append("親しみやすく、優しい相槌や感嘆表現（例：『ふふっ』『そうだね』）を少し交えて応答してください")
        elif v < -0.5:
            hints.append("簡潔に、1文以内の最小限の言葉で応答してください")
            if a > 0.4:
                hints.append(
                    "発話の冒頭や途中に、イライラを表す感嘆詞（例：『はぁ…』『もう！』）を交え、不機嫌でぶっきらぼうに応答してください"
                )
            else:
                hints.append(
                    "発話の冒頭や途中に、落胆を表す感嘆表現（例：『はぁ…』『ふぅ』）を交えて、冷淡に応答してください"
                )
        elif v < -0.2:
            hints.append("やや控えめに、1文程度の短い言葉で応答してください")
            hints.append(
                "発話の冒頭や途中に、元気がなさそうな感嘆詞（例：『うう…』『え〜ん』『しゅん…』）を自然に交え、悲しそうに応答してください"
            )

    @staticmethod
    def _build_arousal_hints(a: float, hints: list[str]) -> None:
        if a > 0.6:
            hints.append("テンポ良く、1〜2文の短い言葉で活発に応答してください")
            hints.append("焦りや興奮を言葉の端々に表し、感嘆符『！』を多めに使ってテンポ良く応答してください")
        elif a < 0.2:
            hints.append("ゆったりとしたペースで、1〜2文程度で応答してください")

    @staticmethod
    def _build_dominance_hints(d: float, hints: list[str]) -> None:
        if d > 0.6:
            hints.append("自信を持って明確に応答してください")
        elif d < 0.3:
            hints.append("慎重に、確認しながら応答してください")
