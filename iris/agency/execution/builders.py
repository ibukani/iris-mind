from __future__ import annotations

from typing import TYPE_CHECKING

from langchain_core.messages import BaseMessage

from iris.agency.execution.state import ExecutionState

if TYPE_CHECKING:
    from iris.agency.planning.models import Plan


def build_execution_state(
    plan: Plan,
    messages: list[BaseMessage],
) -> ExecutionState:
    return ExecutionState(
        plan=plan,
        messages=messages,
        response_text="",
        tool_iterations=0,
        interrupted=False,
        error=None,
        completed=False,
        current_node_type="general_chat",
        current_level_idx=0,
        chain_depth=0,
    )
