from __future__ import annotations

import logging
import time
from datetime import UTC, datetime

from iris.agency.bus import InternalBus, PlanDecided
from iris.agency.execution.inhibition import GateVerdict, InhibitionController
from iris.agency.planning.scoring import ProactiveScoring
from iris.event.event_bus import EventBus
from iris.event.event_types import InputReady
from iris.kernel.config import Config
from iris.memory.manager import MemoryManager

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
    ) -> None:
        self._bus = internal_bus
        self._inhibition = inhibition
        self._scoring = scoring
        self._memory = memory
        self._cfg = config.proactive
        event_bus.subscribe("InputReady", self._on_input_ready)

    def _on_input_ready(self, event: InputReady) -> None:
        context = event.context or {}
        gate = self._inhibition.evaluate(time.time())

        if context.get("from_timer"):
            logger.debug("Timer-triggered input: gate_suppressed=%s score=%.3f", gate.suppressed, gate.score)
            if gate.suppressed:
                return
            total, scores = self._scoring.compute(
                now=time.time(),
                last_proactive_time=self._inhibition.last_proactive_time,
                last_user_activity=self._inhibition.last_user_activity,
                negative_mood_score=self._inhibition.negative_mood_score,
            )
            if total < self._cfg.speak_threshold:
                logger.debug("Below speak_threshold: total=%.3f < threshold=%.2f", total, self._cfg.speak_threshold)
                return
            self._inhibition.record_proactive_attempt()
            context = {
                "from_timer": True,
                "salience": total,
                "scores": scores,
                "context_hint": self._build_context_hint(scores),
            }
            logger.debug("Proactive plan published: total=%.3f scores=%s", total, scores)
        else:
            self._inhibition.notify_user_activity()

        plan = self._build_plan(event.content, context, gate)
        plan["session_id"] = event.session_id
        self._bus.publish(PlanDecided(plan=plan))

    def _build_plan(self, content: str, context: dict, gate: GateVerdict) -> dict:
        """ユーザー入力またはタイマートリガーに基づいて実行計画を構築する。

        計画は LLMPipeline で処理される際に、状況（situation）やコンテキスト、
        抑制制御（gate）の情報を含む。

        Args:
            content: ユーザー入力コンテンツ。タイマートリガーの場合は空文字。
            context: 背景情報。from_timer, salience, scores, context_hint など。
            gate: 基底核抑制制御の評決（suppressed, score）。

        Returns:
            計画辞書。session_id 以外のキーは content, situation, context_hint,
            abbreviated, max_tokens, temperature, tools_allowed など。
        """
        from_timer = context.get("from_timer", False)

        if from_timer:
            scores = context.get("scores", {})
            return {
                "content": "",
                "situation": "proactive",
                "context_hint": context.get("context_hint", ""),
                "scores": scores,
                "total_score": context.get("salience", 0.0),
                "trigger_type": max(scores, key=lambda k: scores[k]) if scores else "unknown",
                "abbreviated": False,
                "tools_allowed": False,
                "streaming": False,
                "max_tokens": 120,
                "temperature": 0.8,
                "show_thinking": False,
                "run_reflexion": False,
                "run_compression": False,
                "record_history": True,
            }

        abbreviated = gate.suppressed or gate.score < self._cfg.abbreviated_threshold
        context_hint = self._build_user_context_hint(content)
        logger.debug(
            "Plan built: abbreviated=%s suppressed=%s gate_score=%.3f", abbreviated, gate.suppressed, gate.score
        )
        return {
            "content": content,
            "context_hint": context_hint,
            "abbreviated": abbreviated,
            "tools_allowed": not abbreviated,
            "streaming": not abbreviated,
            "max_tokens": 80 if abbreviated else 0,
            "temperature": 0.5 if abbreviated else 0.7,
            "show_thinking": not abbreviated,
            "run_reflexion": not abbreviated,
            "run_compression": not abbreviated,
            "record_history": True,
        }

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

    def _build_context_hint(self, scores: dict[str, float]) -> str:
        now = time.localtime()
        hour = now.tm_hour
        time_str = "午前" if hour < 12 else "午後" if hour < 17 else "夕方以降"
        trigger = max(scores, key=lambda k: scores[k])
        parts = [f"時間帯: {time_str}", f"トリガー: {trigger}"]

        if self._memory:
            try:
                recent = self._memory.get_recent(3)
                topics = [
                    f"{e['summary'][:60]}（{self._format_age(e.get('timestamp', ''))}）"
                    for e in recent
                    if e.get("summary")
                ]
                if topics:
                    parts.append("直近の話題: " + " | ".join(topics))
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
