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

        context_hint = self._build_proactive_context_hint(context, scores)
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

    def _build_proactive_context_hint(self, context: dict, scores: dict[str, float]) -> str:
        if "system_event" in context:
            event_name = context.get("system_event")
            offline_duration = context.get("offline_duration", "")
            role = context.get("role", "")
            if event_name == "connected":
                if offline_duration:
                    return f"システムイベント: ロール {role} が {offline_duration} の切断期間を経て再接続しました。"
                return f"システムイベント: ロール {role} が接続しました。"
            return ""
        return self._build_context_hint(
            scores,
            ignore_count=self._inhibition.consecutive_ignores,
            last_user_activity=self._inhibition.last_user_activity,
            last_proactive_time=self._inhibition.last_proactive_time,
            negative_mood_score=self._inhibition.negative_mood_score,
            outputs_since_input=self._inhibition.outputs_since_input,
            frequency_exceeded=self._inhibition.frequency_exceeded,
        )

    def _build_proactive_plan(self, context: dict, gate: GateVerdict, limbic_mood: EmotionState | None = None) -> dict:
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
            self._apply_emotion_to_plan(plan, limbic_mood)
        plan["current_emotion"] = limbic_mood
        return plan

    def _build_response_plan(self, content: str, gate: GateVerdict, limbic_mood: EmotionState | None = None) -> dict:
        abbreviated = gate.suppressed or gate.score < self._cfg.abbreviated_threshold
        context_hint = self._build_user_context_hint(content)
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
            "temperature": 0.5 if abbreviated else self.DEFAULT_TEMPERATURE,
            "show_thinking": not abbreviated and is_task,
            "run_reflexion": not abbreviated and is_task,
            "run_compression": not abbreviated,
            "record_history": True,
        }
        if limbic_mood:
            self._apply_emotion_to_plan(plan, limbic_mood)
        plan["current_emotion"] = limbic_mood
        return plan

    def _is_task_content(self, content: str) -> bool:
        if len(content) > 100 or content.startswith("/"):
            return True
        content_lower = content.lower()
        return any(kw in content_lower for kw in self.TASK_KEYWORDS)

    @classmethod
    def _apply_emotion_to_plan(cls, plan: dict, limbic_mood: EmotionState) -> None:
        v = limbic_mood.valence
        a = limbic_mood.arousal
        d = limbic_mood.dominance

        temp = plan.get("temperature", cls.DEFAULT_TEMPERATURE)

        if v < cls.VALENCE_LOW_THRESHOLD:
            current = plan.get("max_tokens", 0)
            if current > 0:
                plan["max_tokens"] = min(current, 256)
            if plan.get("abbreviated", False) is False:
                temp += cls.TEMP_ADJUST_NEGATIVE_VALENCE
                plan["tools_allowed"] = False
                plan["streaming"] = False
        elif v > cls.VALENCE_HIGH_THRESHOLD:
            temp = max(temp + cls.TEMP_ADJUST_POSITIVE_VALENCE, 0.3)

        if a > cls.AROUSAL_HIGH_THRESHOLD:
            temp = max(temp + cls.TEMP_ADJUST_HIGH_AROUSAL, 0.3)
            current = plan.get("max_tokens", 0)
            if current > 0:
                plan["max_tokens"] = min(current, 256)
        elif a < cls.AROUSAL_LOW_THRESHOLD:
            temp = min(temp + cls.TEMP_ADJUST_LOW_AROUSAL, 1.0)

        if d < cls.DOMINANCE_LOW_THRESHOLD:
            if plan.get("abbreviated", False) and plan["max_tokens"] == 80:
                plan["max_tokens"] = 50
            temp += cls.TEMP_ADJUST_LOW_DOMINANCE
        elif d > cls.DOMINANCE_HIGH_THRESHOLD:
            temp = max(temp + cls.TEMP_ADJUST_HIGH_DOMINANCE, 0.2)
            current = plan.get("max_tokens", 0)
            if current > 0:
                plan["max_tokens"] = min(current, 512)

        plan["temperature"] = max(0.2, min(1.0, temp))

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

    def _build_context_hint(
        self,
        scores: dict[str, float],
        ignore_count: int = 0,
        last_user_activity: float = 0.0,
        last_proactive_time: float = 0.0,
        negative_mood_score: float = 0.0,
        outputs_since_input: int = 0,
        frequency_exceeded: bool = False,
    ) -> str:
        now = time.localtime()
        hour = now.tm_hour
        time_str = "午前" if hour < 12 else "午後" if hour < 17 else "夕方以降"
        trigger = max(scores, key=lambda k: scores[k])
        parts: list[str] = []

        if ignore_count >= 1:
            parts.append(f"呼びかけに応答なし: {ignore_count}回")

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

        if outputs_since_input >= 2:
            parts.append(f"出力: {outputs_since_input}回連続")
        if frequency_exceeded:
            parts.append("出力頻度高")
        if negative_mood_score > 0.3:
            parts.append("気分: 不機嫌")
        elif negative_mood_score > 0.1:
            parts.append("気分: やや不機嫌")

        parts.append(f"時間帯: {time_str}")
        parts.append(f"トリガー: {trigger}")

        wc = self._build_working_context()
        if wc:
            parts.append("ワーキングメモリ:\n" + wc)

        if self._memory:
            try:
                prefs = self._memory.get_user_preferences()
                if prefs:
                    parts.append(f"ユーザーの関心: {prefs[0].get('content', '')[:80]}")
            except Exception:
                logger.debug("Memory hint failed", exc_info=True)

        return " / ".join(parts)

    def _build_user_context_hint(self, content: str) -> str:
        if not self._memory or not content:
            return ""
        parts: list[str] = []
        try:
            wc = self._build_working_context(query=content)
            if wc:
                parts.append(wc)
            else:
                recent = self._memory.get_recent(3)
                for e in reversed(recent):
                    s = e.get("summary", "")
                    ts = self._format_age(e.get("timestamp", ""))
                    if s:
                        label = "直前の話題" if ts == "たった今" else "過去の話題"
                        text = f"{label}: {s[:60]}（{ts}）" if ts else f"話題: {s[:60]}"
                        parts.append(text)
                        break

            results = self._memory.search_semantic(content, max_results=2)
            if results:
                best = max(results, key=lambda r: r.get("score", 0))
                if best.get("score", 0) > 0.5:
                    ts = self._format_age(best.get("timestamp", ""))
                    label = f"関連記憶: {best.get('content', '')[:60]}"
                    if ts:
                        label += f"（{ts}）"
                    parts.append(label)
        except Exception:
            logger.debug("User context hint failed", exc_info=True)
        return " / ".join(parts)
