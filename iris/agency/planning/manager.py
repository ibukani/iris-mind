from __future__ import annotations

from datetime import UTC, datetime
import logging
import time
from typing import TYPE_CHECKING, Any

from iris.agency.bus import InternalBus, PlanDecided
from iris.agency.execution.inhibition import GateVerdict, InhibitionController
from iris.agency.planning.scoring import ProactiveScoring
from iris.event.event_bus import EventBus
from iris.event.event_types import InputReady
from iris.kernel.config import Config
from iris.memory.manager import MemoryManager

if TYPE_CHECKING:
    from iris.limbic.manager import LimbicManager
    from iris.limbic.models import EmotionState

logger = logging.getLogger(__name__)


class EmotionTemperatureModulator:
    VALENCE_LOW_THRESHOLD = -0.3
    VALENCE_HIGH_THRESHOLD = 0.5
    AROUSAL_HIGH_THRESHOLD = 0.6
    AROUSAL_LOW_THRESHOLD = 0.15
    DOMINANCE_LOW_THRESHOLD = 0.3
    DOMINANCE_HIGH_THRESHOLD = 0.6

    TEMP_ADJUST_NEGATIVE_VALENCE = 0.15
    TEMP_ADJUST_POSITIVE_VALENCE = -0.1
    TEMP_ADJUST_HIGH_AROUSAL = -0.15
    TEMP_ADJUST_LOW_AROUSAL = 0.2
    TEMP_ADJUST_LOW_DOMINANCE = 0.05
    TEMP_ADJUST_HIGH_DOMINANCE = -0.1

    DEFAULT_TEMPERATURE = 0.7

    @staticmethod
    def apply(plan: dict[str, Any], limbic_mood: EmotionState) -> None:
        temp: float = plan.get("temperature", EmotionTemperatureModulator.DEFAULT_TEMPERATURE)
        temp = EmotionTemperatureModulator._apply_valence_temp(plan, limbic_mood, temp)
        temp = EmotionTemperatureModulator._apply_arousal_temp(plan, limbic_mood, temp)
        temp = EmotionTemperatureModulator._apply_dominance_temp(plan, limbic_mood, temp)
        plan["temperature"] = max(0.2, min(1.0, temp))

    @staticmethod
    def _apply_valence_temp(plan: dict[str, Any], mood: EmotionState, temp: float) -> float:
        v = mood.valence
        if v < EmotionTemperatureModulator.VALENCE_LOW_THRESHOLD:
            current = plan.get("max_tokens", 0)
            if current > 0:
                plan["max_tokens"] = min(current, 256)
            if plan.get("abbreviated", False) is False:
                plan["tools_allowed"] = False
                plan["streaming"] = False
                return temp + EmotionTemperatureModulator.TEMP_ADJUST_NEGATIVE_VALENCE
        elif v > EmotionTemperatureModulator.VALENCE_HIGH_THRESHOLD:
            return max(temp + EmotionTemperatureModulator.TEMP_ADJUST_POSITIVE_VALENCE, 0.3)
        return temp

    @staticmethod
    def _apply_arousal_temp(plan: dict[str, Any], mood: EmotionState, temp: float) -> float:
        a = mood.arousal
        if a > EmotionTemperatureModulator.AROUSAL_HIGH_THRESHOLD:
            current = plan.get("max_tokens", 0)
            if current > 0:
                plan["max_tokens"] = min(current, 256)
            return max(temp + EmotionTemperatureModulator.TEMP_ADJUST_HIGH_AROUSAL, 0.3)
        if a < EmotionTemperatureModulator.AROUSAL_LOW_THRESHOLD:
            return min(temp + EmotionTemperatureModulator.TEMP_ADJUST_LOW_AROUSAL, 1.0)
        return temp

    @staticmethod
    def _apply_dominance_temp(plan: dict[str, Any], mood: EmotionState, temp: float) -> float:
        d = mood.dominance
        if d < EmotionTemperatureModulator.DOMINANCE_LOW_THRESHOLD:
            if plan.get("abbreviated", False) and plan["max_tokens"] == 80:
                plan["max_tokens"] = 50
            return temp + EmotionTemperatureModulator.TEMP_ADJUST_LOW_DOMINANCE
        if d > EmotionTemperatureModulator.DOMINANCE_HIGH_THRESHOLD:
            current = plan.get("max_tokens", 0)
            if current > 0:
                plan["max_tokens"] = min(current, 512)
            return max(temp + EmotionTemperatureModulator.TEMP_ADJUST_HIGH_DOMINANCE, 0.2)
        return temp


class ContextHintBuilder:
    def __init__(self, memory: MemoryManager | None = None) -> None:
        self._memory = memory

    @staticmethod
    def build_time_label() -> str:
        hour = time.localtime().tm_hour
        if hour < 12:
            return "午前"
        if hour < 17:
            return "午後"
        return "夕方以降"

    @staticmethod
    def build_ignore_context(ignore_count: int) -> str | None:
        if ignore_count < 1:
            return None
        return f"呼びかけに応答なし: {ignore_count}回"

    @staticmethod
    def build_timing_context(last_proactive_time: float, last_user_activity: float) -> list[str]:
        parts: list[str] = []
        if last_proactive_time > 0:
            elapsed = time.time() - last_proactive_time
            parts.append(f"直前出力: {int(elapsed)}秒前")
        if last_user_activity > 0:
            elapsed = time.time() - last_user_activity
            if elapsed < 60:
                parts.append("最終ユーザー入力: たった今")
            else:
                parts.append(f"最終ユーザー入力: {int(elapsed // 60)}分前")
        else:
            parts.append("最終ユーザー入力: --")
        return parts

    @staticmethod
    def build_frequency_context(outputs_since_input: int, frequency_exceeded: bool) -> list[str]:
        parts: list[str] = []
        if outputs_since_input >= 2:
            parts.append(f"出力: {outputs_since_input}回連続")
        if frequency_exceeded:
            parts.append("出力頻度高")
        return parts

    @staticmethod
    def build_mood_context(negative_mood_score: float) -> str | None:
        if negative_mood_score > 0.3:
            return "気分: 不機嫌"
        if negative_mood_score > 0.1:
            return "気分: やや不機嫌"
        return None

    def build_proactive_context_hint(
        self,
        context: dict[str, Any],
        scores: dict[str, float],
        inhibition: InhibitionController | None = None,
    ) -> str:
        if "system_event" in context:
            event_name = context.get("system_event")
            offline_duration = context.get("offline_duration", "")
            role = context.get("role", "")
            if event_name == "connected":
                if offline_duration:
                    return f"システムイベント: ロール {role} が {offline_duration} の切断期間を経て再接続しました。"
                return f"システムイベント: ロール {role} が接続しました。"
            return ""
        return self._build_general_hint(scores, inhibition)

    def _build_general_hint(
        self,
        scores: dict[str, float],
        inhibition: InhibitionController | None = None,
    ) -> str:
        ignore_count = inhibition.consecutive_ignores if inhibition else 0
        last_activity = inhibition.last_user_activity if inhibition else 0.0
        last_proactive = inhibition.last_proactive_time if inhibition else 0.0
        mood_score = inhibition.negative_mood_score if inhibition else 0.0
        outputs = inhibition.outputs_since_input if inhibition else 0
        freq_exceeded = inhibition.frequency_exceeded if inhibition else False

        parts: list[str] = []
        trigger = max(scores, key=lambda k: scores[k])

        ignore_ctx = ContextHintBuilder.build_ignore_context(ignore_count)
        if ignore_ctx:
            parts.append(ignore_ctx)

        parts.extend(ContextHintBuilder.build_timing_context(last_proactive, last_activity))
        parts.extend(ContextHintBuilder.build_frequency_context(outputs, freq_exceeded))

        mood_ctx = ContextHintBuilder.build_mood_context(mood_score)
        if mood_ctx:
            parts.append(mood_ctx)

        parts.append(f"時間帯: {ContextHintBuilder.build_time_label()}")
        parts.append(f"トリガー: {trigger}")

        wc = self._build_working_context()
        if wc:
            parts.append("ワーキングメモリ:\n" + wc)

        pref_ctx = self.build_user_preferences_context()
        if pref_ctx:
            parts.append(pref_ctx)

        return " / ".join(parts)

    def build_user_context_hint(self, content: str) -> str:
        if not self._memory or not content:
            return ""
        parts: list[str] = []
        try:
            wc = self._build_working_context(query=content)
            if wc:
                parts.append(wc)
            else:
                ep_hint = self._build_episodic_hint()
                if ep_hint:
                    parts.append(ep_hint)

            sem_hint = self._build_semantic_hint(content)
            if sem_hint:
                parts.append(sem_hint)
        except Exception:
            logger.debug("User context hint failed", exc_info=True)
        return " / ".join(parts)

    def _build_working_context(self, query: str | None = None) -> str:
        if self._memory is None:
            return ""
        try:
            wm = self._memory.short_term.render_context(query=query)
            if wm:
                return wm
            recent = self._memory.get_recent(3)
            topics = [
                f"{e['summary'][:60]}（{self._format_age(e.get('timestamp', ''))}）" for e in recent if e.get("summary")
            ]
            if topics:
                return "直近の話題: " + " | ".join(topics)
        except Exception:
            logger.debug("Working context failed", exc_info=True)
        return ""

    def _build_episodic_hint(self) -> str | None:
        if not self._memory:
            return None
        recent = self._memory.get_recent(3)
        for e in reversed(recent):
            s = e.get("summary", "")
            if not s:
                continue
            ts = self._format_age(e.get("timestamp", ""))
            if ts:
                label = "直前の話題" if ts == "たった今" else "過去の話題"
                return f"{label}: {s[:60]}（{ts}）"
            return f"話題: {s[:60]}"
        return None

    def _build_semantic_hint(self, content: str) -> str | None:
        if not self._memory:
            return None
        results = self._memory.search_semantic(content, max_results=2)
        if not results:
            return None
        best = max(results, key=lambda r: r.get("score", 0))
        if best.get("score", 0) <= 0.5:
            return None
        ts = self._format_age(best.get("timestamp", ""))
        label = f"関連記憶: {best.get('content', '')[:60]}"
        if ts:
            label += f"（{ts}）"
        return label

    def build_user_preferences_context(self) -> str | None:
        if not self._memory:
            return None
        try:
            prefs = self._memory.get_user_preferences()
            if prefs:
                return f"ユーザーの関心: {prefs[0].get('content', '')[:80]}"
        except Exception:
            logger.debug("Memory hint failed", exc_info=True)
        return None

    @staticmethod
    def _format_age(ts: str) -> str:
        if not ts:
            return ""
        try:
            dt = datetime.fromisoformat(ts)
            diff = datetime.now(UTC) - dt
            secs = int(diff.total_seconds())
            if secs < 60:
                return "たった今"
            if secs < 3600:
                return f"{secs // 60}分前"
            if secs < 86400:
                return f"{secs // 3600}時間前"
            days = secs // 86400
            return f"{days}日前" if days > 1 else "昨日"
        except Exception:
            return ""


class PlanningManager:
    TASK_KEYWORDS: frozenset[str] = frozenset(
        {
            "コード",
            "ファイル",
            "実装",
            "作成",
            "修正",
            "テスト",
            "実行",
            "ディレクトリ",
            "adr",
            "ルール",
            "ログ",
            "詳しく",
            "説明",
            "なぜ",
            "どうやって",
            "設計",
        }
    )

    def __init__(
        self,
        internal_bus: InternalBus,
        event_bus: EventBus,
        inhibition: InhibitionController,
        scoring: ProactiveScoring,
        config: Config,
        memory: MemoryManager | None = None,
        limbic: LimbicManager | None = None,
    ) -> None:
        self._bus = internal_bus
        self._inhibition = inhibition
        self._scoring = scoring
        self._memory = memory
        self._limbic = limbic
        self._cfg = config.proactive
        self._context_builder = ContextHintBuilder(memory=memory)
        event_bus.subscribe("InputReady", self._on_input_ready)

    def get_state(self) -> dict:
        gate = self._inhibition.evaluate(time.time())
        return {
            "suppressed": gate.suppressed,
            "reason": gate.reason,
            "go_signal": round(gate.go_signal, 2),
        }

    def _on_input_ready(self, event: InputReady) -> None:
        context = event.context or {}
        limbic_mood = self._resolve_limbic_mood()
        gate = self._inhibition.evaluate(time.time())

        if context.get("from_timer") or "system_event" in context:
            self._handle_proactive_event(event, context, gate, limbic_mood)
            return

        self._inhibition.notify_user_activity()
        plan = self._build_response_plan(event.content, gate, limbic_mood)
        plan["session_id"] = event.session_id
        logger.info(
            "PlanningManager: plan published session=%s from_timer=%s",
            event.session_id,
            False,
        )
        self._bus.publish(PlanDecided(plan=plan))

    def _resolve_limbic_mood(self) -> EmotionState | None:
        if not self._limbic:
            return None
        emotion = self._limbic.current_emotion()
        self._inhibition.apply_limbic_modulation(emotion)
        return emotion

    def _handle_proactive_event(
        self,
        event: InputReady,
        context: dict,
        gate: GateVerdict,
        limbic_mood: EmotionState | None,
    ) -> None:
        if "system_event" in context:
            self._inhibition.set_cooldown(30.0)

        if gate.suppressed:
            logger.debug("Proactive trigger suppressed by gate (system_event=%s)", context.get("system_event"))
            return

        if context.get("from_timer"):
            ignore_detected = self._inhibition.check_ignore()
            if ignore_detected and self._limbic:
                self._limbic.apply_stimulus("ignored", self._inhibition.consecutive_ignores)

        total, scores = self._scoring.compute(
            now=time.time(),
            last_proactive_time=self._inhibition.last_proactive_time,
            last_user_activity=self._inhibition.last_user_activity,
            negative_mood_score=self._inhibition.negative_mood_score,
            limbic_mood=limbic_mood,
            content=event.content,
            context=context,
            ignore_count=self._inhibition.consecutive_ignores,
        )
        if total < self._cfg.speak_threshold:
            logger.debug("Below speak_threshold: total=%.3f < threshold=%.2f", total, self._cfg.speak_threshold)
            return

        self._inhibition.record_proactive_attempt()

        context_hint = self._context_builder.build_proactive_context_hint(context, scores, self._inhibition)
        proactive_context = {
            "from_timer": True,
            "salience": total,
            "scores": scores,
            "context_hint": context_hint,
        }
        logger.debug("Proactive plan published: total=%.3f scores=%s hint=%s", total, scores, context_hint)
        plan = self._build_proactive_plan(proactive_context, gate, limbic_mood)
        plan["session_id"] = event.session_id
        logger.info(
            "PlanningManager: plan published session=%s from_timer=%s",
            event.session_id,
            True,
        )
        self._bus.publish(PlanDecided(plan=plan))

    def _build_proactive_plan(
        self, context: dict, gate: GateVerdict, limbic_mood: EmotionState | None = None
    ) -> dict[str, Any]:
        plan: dict[str, Any] = {
            "content": "",
            "situation": "proactive",
            "model_role": "default",
            "context_hint": context.get("context_hint", ""),
            "abbreviated": False,
            "tools_allowed": False,
            "streaming": False,
            "max_tokens": 512,
            "temperature": 0.8,
            "show_thinking": False,
            "run_reflexion": False,
            "run_compression": False,
            "record_history": True,
        }
        if limbic_mood:
            EmotionTemperatureModulator.apply(plan, limbic_mood)
        plan["current_emotion"] = limbic_mood
        return plan

    def _build_response_plan(
        self, content: str, gate: GateVerdict, limbic_mood: EmotionState | None = None
    ) -> dict[str, Any]:
        abbreviated = gate.suppressed or gate.score < self._cfg.abbreviated_threshold
        context_hint = self._context_builder.build_user_context_hint(content)
        logger.debug(
            "Plan built: abbreviated=%s suppressed=%s gate_score=%.3f", abbreviated, gate.suppressed, gate.score
        )

        is_task = self._is_task_content(content)

        if abbreviated:
            max_tokens = 80
        elif not is_task:
            max_tokens = 120
            context_hint = f"雑談 / {context_hint}" if context_hint else "雑談"
        else:
            max_tokens = 0

        plan: dict[str, Any] = {
            "content": content,
            "model_role": "fast" if abbreviated else "default",
            "context_hint": context_hint,
            "abbreviated": abbreviated,
            "tools_allowed": not abbreviated,
            "streaming": not abbreviated,
            "max_tokens": max_tokens,
            "temperature": 0.5 if abbreviated else EmotionTemperatureModulator.DEFAULT_TEMPERATURE,
            "show_thinking": not abbreviated and is_task,
            "run_reflexion": not abbreviated and is_task,
            "run_compression": not abbreviated,
            "record_history": True,
        }
        if limbic_mood:
            EmotionTemperatureModulator.apply(plan, limbic_mood)
        plan["current_emotion"] = limbic_mood
        return plan

    def _is_task_content(self, content: str) -> bool:
        if len(content) > 100 or content.startswith("/"):
            return True
        content_lower = content.lower()
        return any(kw in content_lower for kw in self.TASK_KEYWORDS)
