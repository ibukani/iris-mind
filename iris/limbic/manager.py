from __future__ import annotations

from collections.abc import Callable
import logging
import time
from typing import Any, Protocol, TypedDict, runtime_checkable

from iris.event.event_bus import EventBus
from iris.event.event_types import MessageEvent, TimerTick
from iris.limbic.acc import AnteriorCingulateCortex
from iris.limbic.amygdala import Amygdala
from iris.limbic.emotional_memory import EmotionalMemory
from iris.limbic.models import EmotionState


class _MoodEntry(TypedDict):
    condition: Callable[[EmotionState], bool]
    text: str
    short: str


@runtime_checkable
class BigFiveProvider(Protocol):
    """Big Five スコア提供インターフェース（循環import回避）。"""

    def get_scores(self) -> dict[str, float]: ...


logger = logging.getLogger(__name__)

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


class LimbicManager:
    """大脳辺縁系: 感情状態管理、EventBus 連携、他層との統合を行うクラス。

    島皮質 (Insula) 相当の内部状態認識や、扁桃体（感情評価）、前帯状皮質（葛藤制御・調整）を統括する。
    """

    def __init__(
        self,
        event_bus: EventBus | None,
        amygdala: Amygdala | None = None,
        acc: AnteriorCingulateCortex | None = None,
        emotional_memory: EmotionalMemory | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._amygdala = amygdala or Amygdala()
        self._acc = acc or AnteriorCingulateCortex()
        self._emotional_memory = emotional_memory or EmotionalMemory()
        self._emotion = EmotionState()
        self._big_five_provider: BigFiveProvider | None = None

        self._last_decay_time: float = time.time()

        if event_bus is not None:
            event_bus.subscribe("MessageEvent", self._on_message_event)
            event_bus.subscribe("TimerTick", self._on_timer_tick)

    def _on_message_event(self, event: MessageEvent) -> None:
        """メッセージイベント受信時に感情評価を実行する。

        メッセージの入力テキストに基づいて扁桃体で感情の変位（delta）を評価し、
        前帯状皮質で性格特性などを加味して感情を調整・適用し、感情メモリへのタグ付けを行う。
        """
        if not event.content:
            return
        if event.direction not in ("request", "event") or event.msg_type not in ("chat", "system"):
            return
        self._decay()
        delta = self._amygdala.evaluate(event.content)
        adjusted = self._acc.regulate(delta, self._emotion, self._get_big_five_scores())
        self._emotion.apply(adjusted)
        self._emotional_memory.tag(event.content[:200], self._emotion)
        logger.debug(
            "Limbic: input evaluated -> emotion=%s",
            self._emotion.to_dict(),
        )

    def _on_timer_tick(self, event: TimerTick) -> None:
        """タイマーイベント発生時に感情の自然減衰を実行する。

        6回のTickごとに感情を減衰させる。
        """
        if event.tick_count % 6 == 0:
            self._decay()

    def _decay(self) -> None:
        """前回の更新からの経過時間に基づき感情状態を自然減衰（平穏へと近づける）させる。"""
        now = time.time()
        self._emotion.decay(now - self._last_decay_time)
        self._last_decay_time = now

    # === 公開インターフェース ===

    def current_emotion(self) -> EmotionState:
        """現在の感情状態を取得する。"""
        self._decay()
        return self._emotion

    def build_mood_description(self, style: str = "full") -> str:
        """現在の感情状態から自然言語での気分説明を生成する。

        島皮質 (Insula) 相当: 内部状態の言語化。

        Args:
            style: "full" で完全な文章、"short" で簡潔なラベル

        Returns:
            気分説明テキスト。中立時は空文字。
        """
        e = self.current_emotion()
        if abs(e.valence) < 0.1 and e.arousal < 0.15 and abs(e.dominance - 0.5) < 0.1:
            return ""
        for entry in _MOOD_DESCRIPTIONS:
            if entry["condition"](e):
                return entry["short"] if style == "short" else entry["text"]
        return ""

    def build_response_style(self) -> str:
        """感情状態に基づく応答スタイル指示を生成する。

        島皮質+前頭前野が感情状態を言語化し、応答のトーンを調整するための指示文。
        この指示文はシステムプロンプトに注入される。

        Returns:
            "## 応答スタイル\n{指示}" 形式の文字列。中立時は空文字。
        """
        e = self.current_emotion()
        if abs(e.valence) < 0.1 and e.arousal < 0.15 and abs(e.dominance - 0.5) < 0.1:
            return ""

        hints: list[str] = []

        if e.valence > 0.5:
            hints.append("明るく温かいトーンで応答してください")
        elif e.valence > 0.2:
            hints.append("穏やかで親しみやすいトーンで応答してください")
        elif e.valence < -0.5:
            hints.append("簡潔に、1文以内の最小限の言葉で応答してください")
        elif e.valence < -0.2:
            hints.append("やや控えめに、1文程度の短い言葉で応答してください")

        if e.arousal > 0.6:
            hints.append("テンポ良く、1〜2文の短い言葉で活発に応答してください")
        elif e.arousal < 0.2:
            hints.append("ゆったりとしたペースで、1〜2文程度で応答してください")

        if e.dominance > 0.6:
            hints.append("自信を持って明確に応答してください")
        elif e.dominance < 0.3:
            hints.append("慎重に、確認しながら応答してください")

        if not hints:
            return ""

        return "## 応答スタイル\n" + "\n".join(f"- {h}" for h in hints)

    def search_by_emotion(self, max_results: int = 5) -> list[dict[str, Any]]:
        """現在の感情状態に近い感情タグ付き記憶を検索する。"""
        return self._emotional_memory.search_by_emotion(self.current_emotion(), max_results)

    def get_emotion_report(self) -> dict[str, Any]:
        """感情状態のレポートを返す（デバッグ/ステータス用）。"""
        e = self.current_emotion()
        return {
            "emotion": e.to_dict(),
            "mood_text": self.build_mood_description(style="full"),
            "recent_tags": self._emotional_memory.get_recent_tags(3),
        }

    def _get_big_five_scores(self) -> dict[str, float] | None:
        """Big Five プロバイダから性格スコアの辞書を取得する。"""
        if self._big_five_provider is not None:
            return self._big_five_provider.get_scores()
        return None

    def set_big_five(self, big_five: BigFiveProvider | dict[str, float] | None) -> None:
        """Big Five 性格スコアソースを設定する。"""
        if isinstance(big_five, dict):

            class _StaticProvider:
                def get_scores(self) -> dict[str, float]:
                    return big_five  # type: ignore[return-value]

            self._big_five_provider = _StaticProvider()
        elif isinstance(big_five, BigFiveProvider):
            self._big_five_provider = big_five
        else:
            self._big_five_provider = None
