from __future__ import annotations

import math
import time
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from iris.memory.persona_profile import PersonaProfile

from loguru import logger

from iris.event.event_bus import EventBus
from iris.event.event_types import DebugSnapshotEvent, MessageEvent, ProactiveResultEvent, TimerTick
from iris.limbic.amygdala.evaluator import Amygdala
from iris.limbic.cingulate.regulator import AnteriorCingulateCortex
from iris.limbic.hippocampus.binder import EmotionalMemory
from iris.limbic.models import DriveState, EmotionDelta, EmotionState
from iris.limbic.mood import MoodEngine
from iris.limbic.state import PsychometricState

_LABEL_WORDS: frozenset[str] = frozenset(
    {
        "嬉しい",
        "悲しい",
        "怒って",
        "怖い",
        "楽しい",
        "つらい",
        "happy",
        "sad",
        "angry",
        "scared",
        "excited",
        "anxious",
        "lonely",
    }
)


@runtime_checkable
class BigFiveProvider(Protocol):
    """Big Five スコア提供インターフェース（循環import回避）。"""

    def get_scores(self) -> dict[str, float]: ...


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
        self._mood_engine = MoodEngine()
        self._big_five_provider: BigFiveProvider | None = None
        self._persona_profile: PersonaProfile | None = None
        self._psychometric_state: PsychometricState | None = None

        self._last_decay_time: float = time.time()
        self._last_delta: EmotionDelta | None = None
        self._inertia: float = 1.0

        if event_bus is not None:
            event_bus.subscribe("MessageEvent", self._on_message_event)
            event_bus.subscribe("TimerTick", self._on_timer_tick)
            event_bus.subscribe("MonitorFeedback", self._on_monitor_event)
            event_bus.subscribe("ProactiveResultEvent", self._on_proactive_result)

    def set_persona_profile(self, persona_profile: PersonaProfile) -> None:
        self._persona_profile = persona_profile

    def set_psychometric_state(self, state: PsychometricState) -> None:
        self._psychometric_state = state

    def flush_state(self) -> None:
        if self._psychometric_state is not None:
            self._psychometric_state.flush()
            logger.debug("Limbic: psychometric state flushed")

    @staticmethod
    def _has_affect_label(text: str) -> bool:
        return any(w in text.lower() for w in _LABEL_WORDS)

    def _trigger_emotional_reflection(self, delta: EmotionDelta) -> None:
        estimate: dict[str, float] = {}
        if delta.valence > 0:
            estimate["openness"] = 50 + delta.valence * 12
            estimate["extraversion"] = 50 + delta.valence * 15
        elif delta.valence < 0:
            estimate["neuroticism"] = 50 + abs(delta.valence) * 10
            estimate["agreeableness"] = 50 - abs(delta.valence) * 8

        if not estimate:
            return

        if hasattr(self._big_five_provider, "update_from_estimate"):
            changes = self._big_five_provider.update_from_estimate(estimate, "emotional_trigger")  # type: ignore[union-attr]
            if changes:
                logger.info("Limbic: PEM update from emotional trigger -> {}", changes)

        self._publish_snapshot("emotional_reflection")

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

    def _apply_emotion_change(self, delta: EmotionDelta, trigger: str, affect_labeling: bool = False) -> None:
        self._decay()
        adjusted = self._acc.modulate(delta, self._emotion, self._get_big_five_scores())

        # 干渉効果: deltaが現在の感情方向と一致→増幅、逆→減衰（量子認知干渉項）
        alignment = _emotion_alignment(adjusted, self._emotion)
        interference = 1.0 + 0.3 * alignment
        adjusted = adjusted.scale(interference)

        # 感情慣性: 直近のdelta方向と一致→促進、反転→減衰
        if self._last_delta is not None:
            with_last = _delta_alignment(adjusted, self._last_delta)
            if with_last > 0.35:
                self._inertia = min(1.5, self._inertia + 0.15)
            elif with_last < -0.35:
                self._inertia = max(0.3, self._inertia - 0.25)
            else:
                self._inertia += (1.0 - self._inertia) * 0.2
            # 慣性の性格変調: Neuroticism→不安定化、Conscientiousness→安定化
            scores = self._get_big_five_scores()
            if scores:
                neuroticism = scores.get("neuroticism", 50) / 100.0
                conscientiousness = scores.get("conscientiousness", 50) / 100.0
                neuro_factor = 1.0 - (neuroticism - 0.5) * 0.4
                self._inertia *= max(0.5, neuro_factor)
                con_factor = 0.5 + conscientiousness
                self._inertia *= max(0.5, con_factor)
                self._inertia = max(0.3, min(1.5, self._inertia))
            adjusted = adjusted.scale(self._inertia)
        else:
            self._inertia = 1.0
        self._last_delta = adjusted

        # 感情ラベリング効果: ユーザが感情名を明示→前頭前野が扁桃体反応を抑制
        if affect_labeling:
            adjusted = adjusted.scale(0.85)

        self._emotion.apply(adjusted)
        self._publish_snapshot(trigger)

        # 極端な感情→自己内省→PEM更新
        if abs(self._emotion.valence) > 0.75 and trigger not in ("contagion", "retrieval_induced", "drive_coupling"):
            self._trigger_emotional_reflection(delta)

    def _on_message_event(self, event: MessageEvent) -> None:
        if not event.content:
            return
        if event.direction not in ("request", "event") or event.msg_type not in ("chat", "system"):
            return
        delta = self._amygdala.assess(event.content)
        affect_labeling = self._has_affect_label(event.content)
        self._apply_emotion_change(delta, "message", affect_labeling=affect_labeling)

        # 感情伝染: ユーザの感情に15%同調（認知評価とは別経路）
        contagion = self._amygdala.contagion(event.content)
        if contagion.valence != 0:
            self._emotion.apply(contagion)
            self._publish_snapshot("contagion")

        self._emotional_memory.encode(event.content[:200], self._emotion)
        logger.debug("Limbic: input evaluated -> emotion={}", self._emotion.to_dict())

    def _on_timer_tick(self, event: TimerTick) -> None:
        self._drive.accumulate(big_five=self._get_big_five_scores())
        if event.tick_count % 6 == 0:
            self._decay()
            if self._persona_profile is not None:
                self._persona_profile.persona_data.decay_interests()
        if event.tick_count % 12 == 0:
            self._apply_drive_effects()

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
        logger.debug("Limbic: monitor feedback applied -> emotion={}", self._emotion.to_dict())

    def _on_proactive_result(self, event: ProactiveResultEvent) -> None:
        delta = EmotionDelta()
        if event.success:
            delta.valence += 0.2
            delta.dominance += 0.1
            delta.arousal -= 0.1
            self.satisfy_need("curiosity", 0.3)
        else:
            delta.valence -= 0.15
            delta.arousal += 0.2
            delta.dominance -= 0.1

        self._apply_emotion_change(delta, "proactive_result")
        logger.debug(
            "Limbic: proactive result applied -> success=%s emotion=%s", event.success, self._emotion.to_dict()
        )

    # === 公開インターフェース ===

    def _apply_drive_effects(self) -> None:
        needs = self._drive.get_dominant_needs()
        delta = EmotionDelta()
        for name, value in needs:
            if name == "curiosity" and value > 0.7:
                delta.valence -= 0.03 * (value - 0.7) * 2
                delta.arousal += 0.02 * (value - 0.7)
            elif name == "social_need" and value > 0.7:
                delta.valence -= 0.02 * (value - 0.7) * 2
            elif name == "maintenance" and value > 0.8:
                delta.dominance -= 0.02 * (value - 0.8) * 2
        if delta.valence != 0 or delta.arousal != 0 or delta.dominance != 0:
            self._apply_emotion_change(delta, "drive_coupling")

    def get_state(self) -> dict:
        e = self.current_emotion()
        return {
            "emotion": e.to_dict(),
            "drive": self._drive.to_dict(),
            "mood": self.describe_mood(style="short"),
        }

    def current_emotion(self) -> EmotionState:
        """現在の感情状態を取得する。"""
        self._decay()
        return self._emotion

    def current_needs(self) -> DriveState:
        """現在の欲求状態を取得する。"""
        return self._drive

    def satisfy_need(self, need_type: str, amount: float) -> None:
        """特定の行動による欲求の解消を行う。"""
        self._drive.satisfy(need_type, amount)
        self._publish_snapshot(f"satisfy_{need_type}")

    def describe_mood(self, style: str = "full") -> str:
        return self._mood_engine.describe_mood(self.current_emotion(), style)

    def generate_response_style(self, context: str = "") -> str:
        return self._mood_engine.generate_response_style(self.current_emotion(), context)

    def retrieve_memories_by_affect(self, max_results: int = 5) -> list[dict[str, Any]]:
        """現在の感情状態に近い感情タグ付き記憶を検索する。"""
        entries = self._emotional_memory.retrieve_by_affect(self.current_emotion(), max_results)
        # 想起誘発感情: 検索した記憶のvalenceが現在の感情に微量波及
        if entries:
            vals = []
            for e in entries:
                meta = e.get("metadata", {})
                emotion = meta.get("emotion") if isinstance(meta, dict) else {}
                v = float(emotion.get("valence", 0)) if isinstance(emotion, dict) else 0
                vals.append(v)
            if vals:
                avg_v = sum(vals) / len(vals)
                if abs(avg_v) > 0.3:
                    ripple = EmotionDelta(valence=avg_v * 0.05, arousal=0, dominance=0)
                    self._emotion.apply(ripple)
                    self._publish_snapshot("retrieval_induced")
        return entries

    def get_report(self) -> dict[str, Any]:
        """感情状態のレポートを返す（デバッグ/ステータス用）。"""
        e = self.current_emotion()
        return {
            "emotion": e.to_dict(),
            "mood_text": self.describe_mood(style="full"),
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
        logger.debug("Limbic: stimulus {} applied -> emotion={}", stimulus_type, self._emotion.to_dict())

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


def _emotion_alignment(delta: EmotionDelta, state: EmotionState) -> float:
    """deltaと現在の感情状態の方向一致度 [-1, 1]。

    量子認知: 干渉項の位相角に対応。一致→建設的干渉、不一致→破壊的干渉。
    """
    d_mag = math.sqrt(delta.valence**2 + delta.arousal**2 + delta.dominance**2)
    s_mag = math.sqrt(state.valence**2 + state.arousal**2 + state.dominance**2)
    if d_mag * s_mag == 0:
        return 0.0
    dot = delta.valence * state.valence + delta.arousal * state.arousal + delta.dominance * state.dominance
    return dot / (d_mag * s_mag)


def _delta_alignment(a: EmotionDelta, b: EmotionDelta) -> float:
    """2つのdelta間の方向一致度 [-1, 1]。慣性用。"""
    a_mag = math.sqrt(a.valence**2 + a.arousal**2 + a.dominance**2)
    b_mag = math.sqrt(b.valence**2 + b.arousal**2 + b.dominance**2)
    if a_mag * b_mag == 0:
        return 0.0
    dot = a.valence * b.valence + a.arousal * b.arousal + a.dominance * b.dominance
    return dot / (a_mag * b_mag)
