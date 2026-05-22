from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from iris.agency.execution.inhibition import GateVerdict, InhibitionController
    from iris.agency.planning.context_hint import ContextHintBuilder
    from iris.agency.planning.decisions.scoring import ProactiveScoring
    from iris.event.event_types import InputReady
    from iris.kernel.config import ProactiveConfig
    from iris.limbic.manager import LimbicManager
    from iris.limbic.models import DriveState, EmotionState

logger = logging.getLogger(__name__)


class ProactiveJudge:
    def __init__(
        self,
        inhibition: InhibitionController,
        scoring: ProactiveScoring,
        config: ProactiveConfig,
        limbic: LimbicManager | None = None,
        context_builder: ContextHintBuilder | None = None,
    ) -> None:
        self._inhibition = inhibition
        self._scoring = scoring
        self._cfg = config
        self._limbic = limbic
        self._context_builder = context_builder

    def evaluate(
        self,
        event: InputReady,
        context: dict[str, Any],
        gate: GateVerdict,
        limbic_mood: EmotionState | None,
        limbic_drive: DriveState | None = None,
    ) -> dict[str, Any] | None:
        if context.get("escalation"):
            return self._build_escalation_context(context)

        if "system_event" in context:
            self._inhibition.set_cooldown(30.0)

        if gate.suppressed:
            logger.debug("Proactive trigger suppressed by gate (system_event=%s)", context.get("system_event"))
            return None

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
            limbic_drive=limbic_drive,
            content=event.content,
            context=context,
            ignore_count=self._inhibition.consecutive_ignores,
        )
        if total < self._cfg.speak_threshold:
            logger.debug("Below speak_threshold: total=%.3f < threshold=%.2f", total, self._cfg.speak_threshold)
            return None

        topic = "general"
        if limbic_drive:
            dominant = limbic_drive.get_dominant_needs()
            if dominant:
                topic = dominant[0][0]

        drive_score = scores.get("drive", 0.0)
        is_silent_proactive = drive_score > 0.3 and scores.get("context", 0.0) < 0.2
        if is_silent_proactive:
            if self._inhibition.is_topic_suppressed(topic, time.time()):
                logger.debug("Proactive investigation for topic '%s' is suppressed by cooldown", topic)
                return None
            self._inhibition.record_topic(topic, 3600.0)

        self._inhibition.record_proactive_attempt()

        context_hint = (
            self._context_builder.build_proactive_context_hint(context, scores, self._inhibition)
            if self._context_builder
            else ""
        )
        logger.debug("Proactive plan published: total=%.3f scores=%s hint=%s", total, scores, context_hint)
        return {
            "from_timer": True,
            "salience": total,
            "scores": scores,
            "context_hint": context_hint,
            "topic": topic,
            "is_silent_proactive": is_silent_proactive,
        }

    def _build_escalation_context(self, context: dict[str, Any]) -> dict[str, Any]:
        topic = context.get("topic", "general")
        summary = context.get("summary", "")
        context_hint = f"自律調査によるエスカレーション / トピック: {topic} / 調査のまとめ: {summary}"
        logger.info("Publishing escalation proactive plan for topic: %s", topic)
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
