from __future__ import annotations

from typing import TYPE_CHECKING, Any

from iris.agency.planning.emotion_temperature import EmotionTemperatureModulator
from iris.agency.planning.models import Plan, PlanReason
from iris.agency.planning.task_content import is_task_content

if TYPE_CHECKING:
    from iris.agency.inhibition import GateVerdict
    from iris.agency.planning.context_hint_builder import ContextHintBuilder
    from iris.kernel.config import ProactiveConfig
    from iris.limbic.models import EmotionState

from loguru import logger


class ResponsePlanStrategy:
    def __init__(self, config: ProactiveConfig, context_builder: ContextHintBuilder) -> None:
        self._cfg = config
        self._context_builder = context_builder

    def build_response(self, content: str, gate: GateVerdict, limbic_mood: EmotionState | None = None) -> Plan:
        abbreviated = gate.suppressed or gate.score < self._cfg.abbreviated_threshold
        context_hint = self._context_builder.build_user_context_hint(content)

        is_task = is_task_content(content)

        if abbreviated:
            level = 1
        elif not is_task:
            level = 2
        else:
            level = 3

        logger.debug(
            "Plan built: level={} abbreviated={} suppressed={} gate_score={:.3f}",
            level,
            abbreviated,
            gate.suppressed,
            gate.score,
        )

        overrides: dict[str, Any] = {
            "context_hint": context_hint,
        }

        if limbic_mood:
            EmotionTemperatureModulator.apply_execution_params(overrides, limbic_mood)

        return Plan(
            content=content,
            task_level=level,
            silent=False,
            reason=PlanReason.USER_INPUT,
            overrides=overrides,
        )
