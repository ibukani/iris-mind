from __future__ import annotations

from typing import TYPE_CHECKING

from iris.agency.execution.state import ExecutionState

if TYPE_CHECKING:
    from iris.agency.execution.engine import ToolEngine
    from iris.agency.execution.regulation.consolidator import Consolidator

from loguru import logger


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

        logger.debug("Tool execution results: %d tools", len(results))

        from langchain_core.messages import ToolMessage

        MAX_TOOL_OUTPUT_LENGTH = 200
        messages = state["messages"]
        for m in messages:
            if isinstance(m, ToolMessage):
                content = str(m.content)
                if len(content) > MAX_TOOL_OUTPUT_LENGTH:
                    m.content = content[:MAX_TOOL_OUTPUT_LENGTH] + "..."

        if self._tool_executor.all_side_effect(results):
            state["tool_iterations"] = 99
            return

        state["tool_iterations"] = state.get("tool_iterations", 0) + 1
