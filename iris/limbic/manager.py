from __future__ import annotations

from collections.abc import Callable
import time
from typing import TYPE_CHECKING, Any, Protocol, TypedDict, runtime_checkable

if TYPE_CHECKING:
    from iris.memory.persona_profile import PersonaProfile

from loguru import logger

from iris.event.event_bus import EventBus
from iris.event.event_types import DebugSnapshotEvent, MessageEvent, ProactiveResultEvent, TimerTick
from iris.limbic.acc import AnteriorCingulateCortex
from iris.limbic.amygdala import Amygdala
from iris.limbic.emotional_memory import EmotionalMemory
from iris.limbic.models import DriveState, EmotionDelta, EmotionState


class _MoodEntry(TypedDict):
    condition: Callable[[EmotionState], bool]
    text: str
    short: str


@runtime_checkable
class BigFiveProvider(Protocol):
    """Big Five スコア提供インターフェース（循環import回避）。"""

    def get_scores(self) -> dict[str, float]: ...


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
        self._drive = DriveState()
        self._big_five_provider: BigFiveProvider | None = None
        self._persona_profile: PersonaProfile | None = None

        self._last_decay_time: float = time.time()

        if event_bus is not None:
            event_bus.subscribe("MessageEvent", self._on_message_event)
            event_bus.subscribe("TimerTick", self._on_timer_tick)
            event_bus.subscribe("MonitorFeedback", self._on_monitor_event)
            event_bus.subscribe("ProactiveResultEvent", self._on_proactive_result)

    def set_persona_profile(self, persona_profile: PersonaProfile) -> None:
        self._persona_profile = persona_profile

    def _publish_snapshot(self, trigger: str) -> None:
        if self._event_bus is not None:
            self._event_bus.publish(
                DebugSnapshotEvent(
                    timestamp=None,
                    source="limbic",
                    category="limbic.emotion",
                    data={
                        "emotion": self._emotion.to_dict(),
                        "drive": self._drive.to_dict(),
                    },
                    trigger=trigger,
                )
            )

    def _apply_emotion_change(self, delta: EmotionDelta, trigger: str) -> None:
        self._decay()
        adjusted = self._acc.regulate(delta, self._emotion, self._get_big_five_scores())
        self._emotion.apply(adjusted)
        self._publish_snapshot(trigger)

    def _on_message_event(self, event: MessageEvent) -> None:
        if not event.content:
            return
        if event.direction not in ("request", "event") or event.msg_type not in ("chat", "system"):
            return
        delta = self._amygdala.evaluate(event.content)
        self._apply_emotion_change(delta, "message")
        self._emotional_memory.tag(event.content[:200], self._emotion)
        logger.debug("Limbic: input evaluated -> emotion=%s", self._emotion.to_dict())

    def _on_timer_tick(self, event: TimerTick) -> None:
        self._drive.accumulate()
        if event.tick_count % 6 == 0:
            self._decay()
            if self._persona_profile is not None:
                self._persona_profile.persona_data.decay_interests()

    def _decay(self) -> None:
        now = time.time()
        old = self._emotion.to_dict()
        self._emotion.decay(now - self._last_decay_time)
        self._last_decay_time = now
        if self._emotion.to_dict() != old:
            self._publish_snapshot("decay")

    def _on_monitor_event(self, event: MessageEvent) -> None:
        content = event.content
        if not content:
            return
        flags = content.split(",")
        delta = EmotionDelta()
        if "talkative" in flags:
            delta.valence -= 0.15
            delta.arousal += 0.2
            delta.dominance -= 0.1
        if "frequency_exceeded" in flags:
            delta.valence -= 0.1
            delta.arousal += 0.3
            delta.dominance -= 0.15
        if delta.valence == 0 and delta.arousal == 0 and delta.dominance == 0:
            return
        self._apply_emotion_change(delta, "monitor_feedback")
        logger.debug("Limbic: monitor feedback applied -> emotion=%s", self._emotion.to_dict())

    def _on_proactive_result(self, event: ProactiveResultEvent) -> None:
        delta = EmotionDelta()
        if event.success:
            # 調査成功: 達成感・満足感
            delta.valence += 0.2
            delta.dominance += 0.1
            delta.arousal -= 0.1
            self.satisfy_drive("curiosity", 0.3)
        else:
            # 調査失敗: フラストレーション
            delta.valence -= 0.15
            delta.arousal += 0.2
            delta.dominance -= 0.1

        self._apply_emotion_change(delta, "proactive_result")
        logger.debug(
            "Limbic: proactive result applied -> success=%s emotion=%s", event.success, self._emotion.to_dict()
        )

    # === 公開インターフェース ===

    def get_state(self) -> dict:
        e = self.current_emotion()
        return {
            "emotion": e.to_dict(),
            "drive": self._drive.to_dict(),
            "mood": self.build_mood_description(style="short"),
        }

    def current_emotion(self) -> EmotionState:
        """現在の感情状態を取得する。"""
        self._decay()
        return self._emotion

    def current_drive(self) -> DriveState:
        """現在の欲求状態を取得する。"""
        return self._drive

    def satisfy_drive(self, need_type: str, amount: float) -> None:
        """特定の行動による欲求の解消を行う。"""
        self._drive.satisfy(need_type, amount)
        self._publish_snapshot(f"satisfy_{need_type}")

    @staticmethod
    def _is_neutral(e: EmotionState) -> bool:
        return abs(e.valence) < 0.1 and e.arousal < 0.15 and abs(e.dominance - 0.5) < 0.1

    def build_mood_description(self, style: str = "full") -> str:
        e = self.current_emotion()
        if self._is_neutral(e):
            return ""
        for entry in _MOOD_DESCRIPTIONS:
            if entry["condition"](e):
                return entry["short"] if style == "short" else entry["text"]
        return ""

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

    def build_response_style(self) -> str:
        e = self.current_emotion()
        if self._is_neutral(e):
            return ""

        hints: list[str] = []
        self._build_valence_hints(e, hints)
        self._build_arousal_hints(e, hints)
        self._build_dominance_hints(e, hints)

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

    def apply_stimulus(self, stimulus_type: str, intensity: float = 1.0) -> None:
        delta = EmotionDelta()
        if stimulus_type == "ignored":
            decay = max(0.05, 0.15 - intensity * 0.02)
            delta.valence -= decay
            delta.dominance -= max(0.05, 0.12 - intensity * 0.015)
            logger.debug(
                "Limbic: ignore stimulus intensity=%d delta=(v=%.3f, d=%.3f)",
                intensity,
                delta.valence,
                delta.dominance,
            )
        if delta.valence == 0 and delta.arousal == 0 and delta.dominance == 0:
            return
        self._apply_emotion_change(delta, "stimulus")
        logger.debug("Limbic: stimulus %s applied -> emotion=%s", stimulus_type, self._emotion.to_dict())

    def set_big_five(self, big_five: BigFiveProvider | dict[str, float] | None) -> None:
        if isinstance(big_five, dict):
            _scores: dict[str, float] = big_five

            class _StaticProvider:
                def get_scores(self) -> dict[str, float]:
                    return _scores

            self._big_five_provider = _StaticProvider()
        elif isinstance(big_five, BigFiveProvider):
            self._big_five_provider = big_five
        else:
            self._big_five_provider = None
