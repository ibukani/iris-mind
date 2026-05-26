from __future__ import annotations

from typing import TYPE_CHECKING

from iris.agency.execution.state import ExecutionState
from iris.agency.planning.models import Plan
from iris.agency.task_level import TASK_LEVELS

if TYPE_CHECKING:
    from iris.agency.execution.regulation.consolidator import Consolidator

from loguru import logger


class PostProcessNode:
    def __init__(
        self,
        consolidator: Consolidator | None = None,
    ) -> None:
        self._consolidator = consolidator

    async def __call__(self, state: ExecutionState) -> None:
        plan: Plan = state["plan"]
        if self._consolidator is None:
            return

        run_reflexion = plan.overrides.get("run_reflexion", TASK_LEVELS[plan.task_level].run_reflexion)
        run_compression = plan.overrides.get("run_compression", TASK_LEVELS[plan.task_level].run_compression)

        try:
            await self._consolidator.run_post_process(run_reflexion, run_compression)
        except Exception:
            logger.exception("Post-process failed")
