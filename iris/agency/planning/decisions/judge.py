from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from iris.agency.planning.context_hint_builder import ContextHintBuilder
    from iris.agency.planning.decisions.scorer import ProactiveScorer, ScoreContext
    from iris.event.event_types import InputReady
    from iris.kernel.config import ProactiveConfig

from loguru import logger

from iris.agency.planning.decisions.scorer import ScoreContext


class ProactiveJudge:
    def __init__(
        self,
        scoring: ProactiveScorer,
        config: ProactiveConfig,
        context_builder: ContextHintBuilder | None = None,
    ) -> None:
        self._scoring = scoring
        self._cfg = config
        self._context_builder = context_builder

    def decide(
        self,
        event: InputReady,
        context: dict[str, Any],
    ) -> dict[str, Any] | None:
        if context.get("escalation"):
            return self._build_escalation_context(context)

        total, scores = self._scoring.compute(
            ScoreContext(
                now=time.time(),
                content=event.content,
                context=context,
            ),
        )
        if total < self._cfg.speak_threshold:
            logger.debug("Below speak_threshold: total={:.3f} < threshold={:.2f}", total, self._cfg.speak_threshold)
            return None

        chaos_level = context.get("chaos_level", 0.0)
        context_hint = (
            self._context_builder.build_proactive_context_hint(
                context, scores, chaos_level=chaos_level, room_id=event.room_id,
            )
            if self._context_builder
            else ""
        )
        logger.debug("Proactive plan published: total={:.3f} scores={} hint={}", total, scores, context_hint)
        return {
            "from_timer": True,
            "salience": total,
            "scores": scores,
            "context_hint": context_hint,
            "topic": "general",
            "is_silent_proactive": False,
            "chaos_level": chaos_level,
        }

    def _build_escalation_context(self, context: dict[str, Any]) -> dict[str, Any]:
        topic = context.get("topic", "general")
        summary = context.get("summary", "")
        context_hint = f"自律調査によるエスカレーション / トピック: {topic} / 調査のまとめ: {summary}"
        logger.info("Publishing escalation proactive plan for topic: {}", topic)
        return {
            "from_timer": True,
            "salience": 1.0,
            "scores": {"curiosity": 1.0},
            "context_hint": context_hint,
            "topic": topic,
            "is_silent_proactive": False,
            "escalation": True,
            "summary": summary,
        }
