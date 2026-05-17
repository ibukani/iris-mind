from __future__ import annotations

import logging
import time

from iris.agency.bus import InternalBus, PlanDecided
from iris.agency.execution.inhibition import GateVerdict, InhibitionController
from iris.agency.planning.scoring import ProactiveScoring
from iris.event.event_bus import EventBus
from iris.event.event_types import InputReady
from iris.kernel.config import Config

logger = logging.getLogger(__name__)


class PlanningManager:
    def __init__(
        self,
        internal_bus: InternalBus,
        event_bus: EventBus,
        inhibition: InhibitionController,
        scoring: ProactiveScoring,
        config: Config,
    ) -> None:
        self._bus = internal_bus
        self._inhibition = inhibition
        self._scoring = scoring
        self._cfg = config.proactive
        event_bus.subscribe("InputReady", self._on_input_ready)

    def _on_input_ready(self, event: InputReady) -> None:
        context = event.context or {}
        gate = self._inhibition.evaluate(time.time())

        if context.get("from_timer"):
            if gate.suppressed:
                return
            total, scores = self._scoring.compute(
                now=time.time(),
                last_proactive_time=self._inhibition.last_proactive_time,
                last_user_activity=self._inhibition.last_user_activity,
                negative_mood_score=self._inhibition.negative_mood_score,
            )
            if total < self._cfg.speak_threshold:
                return
            self._inhibition.record_proactive_attempt()
            context = {
                "from_timer": True,
                "salience": total,
                "scores": scores,
                "context_hint": self._build_context_hint(scores),
            }
        else:
            self._inhibition.notify_user_activity()

        plan = self._build_plan(event.content, context, gate)
        plan["session_id"] = event.session_id
        self._bus.publish(PlanDecided(plan=plan))

    def _build_plan(self, content: str, context: dict, gate: GateVerdict) -> dict:
        from_timer = context.get("from_timer", False)

        if from_timer:
            scores = context.get("scores", {})
            return {
                "content": "",
                "scores": scores,
                "total_score": context.get("salience", 0.0),
                "trigger_type": max(scores, key=lambda k: scores[k]) if scores else "unknown",
                "context_hint": context.get("context_hint", ""),
                "short_prompt": (
                    "あなたはIrisです。ユーザーに自然に声をかけてください。\n\n"
                    "■ ルール:\n"
                    "- 短く（40文字以内）で友好的\n"
                    "- ユーザーのことを推測せず、確実にわかることだけ\n"
                    "- 質問形式より気遣い・報告形式を優先\n"
                    "- 発話内容のみ出力"
                ),
                "short_user_message": "短く自然な一言を生成してください。",
                "abbreviated": False,
                "tools_allowed": False,
                "streaming": False,
                "max_tokens": 80,
                "temperature": 0.5,
                "show_thinking": False,
                "run_reflexion": False,
                "run_compression": False,
                "record_history": True,
            }

        abbreviated = gate.suppressed or gate.score < self._cfg.abbreviated_threshold
        return {
            "content": content,
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
    def _build_context_hint(scores: dict[str, float]) -> str:
        now = time.localtime()
        hour = now.tm_hour
        time_str = "午前" if hour < 12 else "午後" if hour < 17 else "夕方以降"
        trigger = max(scores, key=lambda k: scores[k])
        return f"時間帯: {time_str} / トリガー: {trigger}"
