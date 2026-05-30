from __future__ import annotations

from typing import TYPE_CHECKING, Any

from iris.agency.modulation import ModulationState
from iris.agency.planning.models import Plan, PlanReason
from iris.agency.planning.task_content import is_task_content

if TYPE_CHECKING:
    from iris.agency.planning.context_hint_builder import ContextHintBuilder
    from iris.kernel.config import ProactiveConfig

from loguru import logger


class ResponsePlanStrategy:
    def __init__(self, config: ProactiveConfig, context_builder: ContextHintBuilder) -> None:
        self._cfg = config
        self._context_builder = context_builder

    def build_response(self, content: str, chaos_level: float = 0.0, room_id: str = "") -> Plan:
        context_hint = self._context_builder.build_user_context_hint(content, chaos_level=chaos_level, room_id=room_id)
        is_task = is_task_content(content)

        level = "light" if not is_task else "normal"

        logger.debug("Plan built: level={}", level)

        overrides: dict[str, Any] = {}
        modulation = ModulationState(chaos_level=chaos_level)

        return Plan(
            content=content,
            task_level=level,
            silent=False,
            reason=PlanReason.USER_INPUT,
            context_hint=context_hint,
            overrides=overrides,
            modulation=modulation,
        )
