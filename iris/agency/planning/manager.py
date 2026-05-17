from __future__ import annotations

import logging
import time

from iris.agency.bus import InternalBus, PlanDecided

logger = logging.getLogger(__name__)


class PlanningManager:
    def __init__(self, internal_bus: InternalBus) -> None:
        self._bus = internal_bus
        self._bus.subscribe("ExecutionResult", self._on_result)

    def handle(self, content: str, session_id: str = "", context: dict | None = None) -> None:
        plan = self._decide(content, context or {})
        plan["session_id"] = session_id
        self._bus.publish(PlanDecided(plan=plan))

    def handle_proactive(self, scores: dict[str, float], total: float) -> None:
        trigger_type = max(scores, key=lambda k: scores[k])
        context_hint = self._build_context_hint(scores)
        plan = {
            "action": "proactive",
            "scores": scores,
            "total_score": total,
            "trigger_type": trigger_type,
            "context_hint": context_hint,
        }
        self._bus.publish(PlanDecided(plan=plan))
        logger.info("Proactive plan: trigger=%s score=%.2f", trigger_type, total)

    def _decide(self, content: str, _context: dict) -> dict:
        return {"action": "respond", "content": content}

    def _on_result(self, event: object) -> None:
        pass

    @staticmethod
    def _build_context_hint(scores: dict[str, float]) -> str:
        now = time.localtime()
        hour = now.tm_hour
        time_str = "午前" if hour < 12 else "午後" if hour < 17 else "夕方以降"
        trigger = max(scores, key=lambda k: scores[k])
        return f"時間帯: {time_str} / トリガー: {trigger}"
