from __future__ import annotations

from datetime import UTC, datetime
import logging
import time
from typing import TYPE_CHECKING

from iris.agency.bus import InternalBus, PlanDecided
from iris.agency.execution.inhibition import GateVerdict, InhibitionController
from iris.agency.planning.scoring import ProactiveScoring
from iris.event.event_bus import EventBus
from iris.event.event_types import InputReady
from iris.kernel.config import Config
from iris.memory.manager import MemoryManager

if TYPE_CHECKING:
    from iris.limbic.manager import LimbicManager

logger = logging.getLogger(__name__)


class PlanningManager:
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

    def _on_input_ready(self, event: InputReady) -> None:
        context = event.context or {}

        if self._limbic:
            emotion = self._limbic.current_emotion()
            self._inhibition.apply_limbic_modulation(emotion)
            limbic_mood = emotion.to_dict()
        else:
            limbic_mood = None

        gate = self._inhibition.evaluate(time.time())

        is_system_event = "system_event" in context

        if context.get("from_timer") or is_system_event:
            if is_system_event:
                self._inhibition.set_cooldown(30.0)

            if gate.suppressed:
                logger.debug("Proactive trigger suppressed by gate (system_event=%s)", context.get("system_event"))
                return

            if context.get("from_timer"):
                self._inhibition.check_ignore()

            total, scores = self._scoring.compute(
                now=time.time(),
                last_proactive_time=self._inhibition.last_proactive_time,
                last_user_activity=self._inhibition.last_user_activity,
                negative_mood_score=self._inhibition.negative_mood_score,
                limbic_mood=limbic_mood,
                content=event.content,
                context=context,
            )
            if total < self._cfg.speak_threshold:
                logger.debug("Below speak_threshold: total=%.3f < threshold=%.2f", total, self._cfg.speak_threshold)
                return
            self._inhibition.record_proactive_attempt()

            context_hint = ""
            if is_system_event:
                event_name = context.get("system_event")
                offline_duration = context.get("offline_duration", "")
                role = context.get("role", "")
                if event_name == "connected":
                    if offline_duration:
                        context_hint = (
                            f"システムイベント: ロール {role} が {offline_duration} の切断期間を経て再接続しました。"
                        )
                    else:
                        context_hint = f"システムイベント: ロール {role} が接続しました。"
            else:
                context_hint = self._build_context_hint(scores)

            context = {
                "from_timer": True,
                "salience": total,
                "scores": scores,
                "context_hint": context_hint,
            }
            logger.debug("Proactive plan published: total=%.3f scores=%s hint=%s", total, scores, context_hint)
        else:
            self._inhibition.notify_user_activity()

        plan = self._build_plan(event.content, context, gate, limbic_mood)
        plan["session_id"] = event.session_id
        logger.info(
            "PlanningManager: plan published session=%s from_timer=%s suppressed=%s",
            event.session_id,
            context.get("from_timer", False),
            gate.suppressed,
        )
        self._bus.publish(PlanDecided(plan=plan))

    def _build_plan(
        self, content: str, context: dict, gate: GateVerdict, limbic_mood: dict[str, float] | None = None
    ) -> dict:
        from_timer = context.get("from_timer", False)

        if from_timer:
            scores = context.get("scores", {})
            plan: dict = {
                "content": "",
                "situation": "proactive",
                "model_role": "default",
                "context_hint": context.get("context_hint", ""),
                "scores": scores,
                "total_score": context.get("salience", 0.0),
                "trigger_type": max(scores, key=lambda k: scores[k]) if scores else "unknown",
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

        abbreviated = gate.suppressed or gate.score < self._cfg.abbreviated_threshold
        context_hint = self._build_user_context_hint(content)
        logger.debug(
            "Plan built: abbreviated=%s suppressed=%s gate_score=%.3f", abbreviated, gate.suppressed, gate.score
        )

        # 雑談判定とトークン制限
        is_task = False
        task_keywords = [
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
        ]
        content_lower = content.lower()
        if len(content) > 100 or any(kw in content_lower for kw in task_keywords) or content.startswith("/"):
            is_task = True

        if abbreviated:
            max_tokens = 80
        elif not is_task:
            max_tokens = 120  # 雑談時は短文トークン制限
            context_hint = f"雑談 / {context_hint}" if context_hint else "雑談"
        else:
            max_tokens = 0  # タスク時は制限なし

        plan = {
            "content": content,
            "model_role": "fast" if abbreviated else "default",
            "context_hint": context_hint,
            "abbreviated": abbreviated,
            "tools_allowed": not abbreviated,
            "streaming": not abbreviated,
            "max_tokens": max_tokens,
            "temperature": 0.5 if abbreviated else 0.7,
            "show_thinking": not abbreviated and is_task,  # 雑談時は思考表示をOFF（Neiroライク）
            "run_reflexion": not abbreviated and is_task,  # 雑談時は振り返りもスキップ
            "run_compression": not abbreviated,
            "record_history": True,
        }
        if limbic_mood:
            self._apply_emotion_to_plan(plan, limbic_mood)
        plan["current_emotion"] = limbic_mood
        return plan

    @staticmethod
    def _apply_emotion_to_plan(plan: dict, limbic_mood: dict[str, float]) -> None:
        v = limbic_mood.get("valence", 0.0)
        a = limbic_mood.get("arousal", 0.0)
        d = limbic_mood.get("dominance", 0.5)

        if v < -0.3:
            plan["max_tokens"] = min(plan.get("max_tokens", 0) or 9999, 256)
            if plan.get("abbreviated", False) is False:
                plan["temperature"] = plan.get("temperature", 0.7) + 0.15
                plan["tools_allowed"] = False
                plan["streaming"] = False
        elif v > 0.5:
            plan["temperature"] = max(plan.get("temperature", 0.7) - 0.1, 0.3)

        if a > 0.6:
            plan["temperature"] = max(plan.get("temperature", 0.7) - 0.15, 0.3)
            plan["max_tokens"] = min(plan.get("max_tokens", 0) or 9999, 256)
        elif a < 0.15:
            plan["temperature"] = min(plan.get("temperature", 0.7) + 0.2, 1.0)

        if d < 0.3:
            if plan.get("abbreviated", False) and plan["max_tokens"] == 80:
                plan["max_tokens"] = 50
            plan["temperature"] = plan.get("temperature", 0.7) + 0.05
        elif d > 0.6:
            plan["temperature"] = max(plan.get("temperature", 0.7) - 0.1, 0.2)
            plan["max_tokens"] = min(plan.get("max_tokens", 0) or 9999, 512)

        plan["temperature"] = max(0.2, min(1.0, plan.get("temperature", 0.7)))

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

    def _build_context_hint(self, scores: dict[str, float]) -> str:
        now = time.localtime()
        hour = now.tm_hour
        time_str = "午前" if hour < 12 else "午後" if hour < 17 else "夕方以降"
        trigger = max(scores, key=lambda k: scores[k])
        parts = [f"時間帯: {time_str}", f"トリガー: {trigger}"]

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
