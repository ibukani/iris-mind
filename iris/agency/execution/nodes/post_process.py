from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from iris.agency.execution.state import ExecutionState

if TYPE_CHECKING:
    from iris.agency.execution.regulation.consolidator import Consolidator

logger = logging.getLogger(__name__)


class PostProcessNode:
    def __init__(
        self,
        consolidator: Consolidator | None = None,
    ) -> None:
        self._consolidator = consolidator

    async def __call__(self, state: ExecutionState) -> None:
        plan = state["plan"]
        if self._consolidator is None:
            return

        run_reflexion = plan.get("run_reflexion", False)
        run_compression = plan.get("run_compression", False)

        try:
            self._consolidator.run_post_process(plan, run_reflexion, run_compression)
        except Exception:
            logger.exception("Post-process failed")
