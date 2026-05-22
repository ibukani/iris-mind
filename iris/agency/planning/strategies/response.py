from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from iris.agency.planning.emotion_temperature import EmotionTemperatureModulator
from iris.agency.planning.task_content import is_task_content

if TYPE_CHECKING:
    from iris.agency.execution.inhibition import GateVerdict
    from iris.agency.planning.context_hint_builder import ContextHintBuilder
    from iris.kernel.config import ProactiveConfig
    from iris.limbic.models import EmotionState

logger = logging.getLogger(__name__)


class ResponsePlanStrategy:
    def __init__(self, config: ProactiveConfig, context_builder: ContextHintBuilder) -> None:
        self._cfg = config
        self._context_builder = context_builder

    def build_response(
        self, content: str, gate: GateVerdict, limbic_mood: EmotionState | None = None
    ) -> dict[str, Any]:
        abbreviated = gate.suppressed or gate.score < self._cfg.abbreviated_threshold
        context_hint = self._context_builder.build_user_context_hint(content)
        logger.debug(
            "Plan built: abbreviated=%s suppressed=%s gate_score=%.3f", abbreviated, gate.suppressed, gate.score
        )

        is_task = is_task_content(content)

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
