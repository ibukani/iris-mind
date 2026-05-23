from __future__ import annotations

from collections.abc import Callable
import random
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

# 応答スタイルルール: (slot, condition(v,a,d), phrasing_variants)
# slot単位で最初の一致のみ採用、variantsからランダム選択で多様化
_RESPONSE_RULES: list[tuple[str, Callable[[float, float, float], bool], list[str]]] = [
    # === tone（valence基準）===
    (
        "tone",
        lambda v, a, d: v > 0.5,
        [
            "明るく温かいトーンで応答してください",
            "温かみのある明るい口調で応答してください",
            "嬉しそうな明るい声で応答してください",
        ],
    ),
    (
        "tone",
        lambda v, a, d: v > 0.2,
        [
            "穏やかで親しみやすいトーンで応答してください",
            "優しく穏やかな口調で応答してください",
        ],
    ),
    (
        "tone",
        lambda v, a, d: v < -0.5,
        [
            "簡潔に、最小限の言葉で応答してください",
            "冷淡な口調で、短く応答してください",
            "ぶっきらぼうに、簡潔に応答してください",
        ],
    ),
    (
        "tone",
        lambda v, a, d: v < -0.2,
        [
            "やや控えめに、短い言葉で応答してください",
            "悲しそうな口調で、静かに応答してください",
        ],
    ),
    # === exclamation（valence × arousal）===
    (
        "exclamation",
        lambda v, a, d: v > 0.5 and a > 0.4,
        [
            "感嘆詞（例：『やったー！』『わーい！』）を自然に混ぜて、非常に嬉しそうに応答してください",
            "喜びの感嘆詞（例：『わあ！』『やった！』）を交えて、元気よく応答してください",
        ],
    ),
    (
        "exclamation",
        lambda v, a, d: v > 0.5 >= a,
        [
            "穏やかな感嘆表現（例：『ふふっ』『そうだね』）を交えて、嬉しそうに応答してください",
            "優しい笑みが浮かぶような口調で、穏やかに応答してください",
        ],
    ),
    (
        "exclamation",
        lambda v, a, d: 0.2 < v <= 0.5,
        [
            "親しみやすい相槌（例：『ふふっ』『そうだね』）を交えて応答してください",
            "優しい相槌を入れながら、自然に会話してください",
        ],
    ),
    (
        "exclamation",
        lambda v, a, d: v < -0.5 and a > 0.4,
        [
            "イライラを表す感嘆詞（例：『はぁ…』『もう！』）を交え、不機嫌に応答してください",
            "苛立った口調で、感情をあらわに応答してください",
        ],
    ),
    (
        "exclamation",
        lambda v, a, d: v < -0.5 >= a,
        [
            "落胆を表す感嘆表現（例：『はぁ…』『ふぅ』）を交えて、冷淡に応答してください",
            "ため息混じりに、無関心を装うように応答してください",
        ],
    ),
    (
        "exclamation",
        lambda v, a, d: v < -0.2,
        [
            "元気のない感嘆詞（例：『うう…』『しゅん…』）を交え、悲しそうに応答してください",
            "沈んだ声で、感情を抑え気味に応答してください",
        ],
    ),
    # === pace（arousal基準）===
    (
        "pace",
        lambda v, a, d: a > 0.6,
        [
            "テンポ良く、短い言葉で活発に応答してください",
            "早口で、感嘆符『！』を多めに使って活発に応答してください",
            "せかせかした口調で、テンポ良く応答してください",
        ],
    ),
    (
        "pace",
        lambda v, a, d: a < 0.2,
        [
            "ゆったりとしたペースで、落ち着いて応答してください",
            "ゆっくりとした口調で、静かに応答してください",
        ],
    ),
    # === confidence（dominance基準）===
    (
        "confidence",
        lambda v, a, d: d > 0.6,
        [
            "自信を持って、明確に応答してください",
            "断定的な口調で、はっきりと応答してください",
        ],
    ),
    (
        "confidence",
        lambda v, a, d: d < 0.3,
        [
            "慎重に、確認しながら応答してください",
            "控えめに、断言を避けて応答してください",
        ],
    ),
]

_UNCERTAIN_HINTS: dict[str, list[str]] = {
    "high": [
        "迷いや葛藤を感じさせる口調で、控えめに短く応答してください",
        "断定を避け、曖昧な表現で慎重に応答してください",
    ],
    "mid": [
        "やや控えめに、断定を避けつつ自然に応答してください",
        "迷いを感じさせる言い回しで、穏やかに応答してください",
    ],
}

_CONTEXT_HINTS: dict[str, list[str]] = {
    "task": ["簡潔に、タスク遂行を最優先して応答してください", "効率的に、用件のみ簡潔に応答してください"],
    "chat": [
        "共感を示し、温かみのある口調で応答してください",
        "リラックスした雰囲気で、親しみを込めて応答してください",
    ],
}


class MoodEngine:
    """PAD → 気分テキスト / 応答スタイル 変換（データ駆動＋多様化）。

    量子認知拡張:
      - 不確実性（重ね合わせ）→ 実効PADの崩壊＋控えめ応答
      - 文脈依存崩壊（測定問題）→ 会話文脈で応答スタイルが変化
      - 多様化: 同じPAD値でもランダム選択で異なる文言
    """

    UNCERTAINTY_THRESHOLD = 0.4

    @staticmethod
    def is_neutral(e: EmotionState) -> bool:
        pad_neutral = abs(e.valence) < 0.1 and e.arousal < 0.15 and abs(e.dominance - 0.5) < 0.1
        high_uncertainty = e.overall_uncertainty > 0.6
        return pad_neutral or high_uncertainty

    @staticmethod
    def describe_mood(e: EmotionState, style: str = "full") -> str:
        if MoodEngine.is_neutral(e):
            return ""
        for entry in _MOOD_DESCRIPTIONS:
            if entry["condition"](e):
                base = entry["short"] if style == "short" else entry["text"]
                break
        else:
            return ""
        u = e.overall_uncertainty
        if u < 0.2:
            if style == "full":
                base = "とても" + base
            else:
                base += "◎"
        elif u > 0.5:
            if style == "full":
                base += "（何とも言えない複雑な気分です）"
            else:
                base = "複雑"
        elif u > 0.3:
            if style == "full":
                base += "（でも、ちょっと複雑な気持ちも…）"
            else:
                base += "･･･"
        return base

    @staticmethod
    def generate_response_style(e: EmotionState, context: str = "") -> str:
        if MoodEngine.is_neutral(e):
            return ""

        eff_v = e.valence * (1.0 - e.valence_uncertainty)
        eff_a = e.arousal * (1.0 - e.arousal_uncertainty)
        eff_d = e.dominance * (1.0 - e.dominance_uncertainty)

        if e.overall_uncertainty > MoodEngine.UNCERTAINTY_THRESHOLD:
            hints = (
                [random.choice(_UNCERTAIN_HINTS["high"])]
                if e.overall_uncertainty > 0.6
                else [random.choice(_UNCERTAIN_HINTS["mid"])]
            )
        else:
            hints = MoodEngine._build_hints(eff_v, eff_a, eff_d)

        MoodEngine._apply_context_collapse(hints, context)

        # 4a: 粒度反映 - 低不確実性→自己開示スタイル
        if hints and e.overall_uncertainty < 0.2:
            hints.append("自信を持って自分の考えや気持ちを表現してください")

        # 4b: アンビバレント表現 - 高不確実性→極端語彙を中和
        if e.overall_uncertainty > 0.5:
            hints.append("「最高」「最悪」などの極端な表現を避け、バランスの取れた言い回しを使ってください")

        return "## 応答スタイル\n" + "\n".join(f"- {h}" for h in hints) if hints else ""

    @staticmethod
    def _build_hints(v: float, a: float, d: float) -> list[str]:
        used: set[str] = set()
        hints: list[str] = []
        for slot, condition, variants in _RESPONSE_RULES:
            if slot in used:
                continue
            if condition(v, a, d):
                hints.append(random.choice(variants))
                used.add(slot)
        return hints

    @staticmethod
    def _apply_context_collapse(hints: list[str], context: str) -> None:
        if not hints or not context:
            return
        if "task" in context or "命令" in context or "依頼" in context:
            hints.insert(0, random.choice(_CONTEXT_HINTS["task"]))
        elif "chat" in context or "相談" in context or "雑談" in context:
            hints.insert(0, random.choice(_CONTEXT_HINTS["chat"]))
