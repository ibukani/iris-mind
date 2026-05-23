from __future__ import annotations

from typing import TYPE_CHECKING

from langchain_core.messages import ToolMessage

from iris.agency.execution.state import ExecutionState

if TYPE_CHECKING:
    from iris.agency.execution.engine import ToolEngine
    from iris.agency.execution.regulation.consolidator import Consolidator

from loguru import logger

_MAX_TOOL_OUTPUT_LENGTH = 200


class ToolRunNode:
    def __init__(
        self,
        tool_executor: ToolEngine | None = None,
        consolidator: Consolidator | None = None,
    ) -> None:
        self._tool_executor = tool_executor
        self._consolidator = consolidator

    async def __call__(self, state: ExecutionState) -> None:
        if self._tool_executor is None:
            return

        results = self._tool_executor.run_tool_calls(state["messages"])
        if self._consolidator:
            self._consolidator.record_activity()

        logger.debug("Tool execution results: {} tools", len(results))

        self._truncate_tool_outputs(state)
        self._check_iterations(results, state)

    def _truncate_tool_outputs(self, state: ExecutionState) -> None:
        messages = state["messages"]
        for m in messages:
            if isinstance(m, ToolMessage):
                content = str(m.content)
                if len(content) > _MAX_TOOL_OUTPUT_LENGTH:
                    m.content = content[:_MAX_TOOL_OUTPUT_LENGTH] + "..."

    @staticmethod
    def _check_iterations(
        results: list,
        state: ExecutionState,
    ) -> None:
        if results and all(r[2] for r in results):
            state["tool_iterations"] = 99
        else:
            state["tool_iterations"] = state.get("tool_iterations", 0) + 1
