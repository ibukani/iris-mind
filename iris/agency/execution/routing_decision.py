from __future__ import annotations

from dataclasses import dataclass

from iris.agency.execution.models import ExecutionState
from iris.agency.execution.node_type import NODE_TYPES
from iris.agency.task_level import TASK_LEVELS


@dataclass(frozen=True)
class RouteDecision:
    next_node: str
    set_node_type: str | None = None
    set_chain_depth: int | None = None
    set_level_idx: int | None = None


def decide_next_route(state: ExecutionState) -> RouteDecision:
    if state.get("interrupted") or state.get("error"):
        return RouteDecision(next_node="finalize")

    messages = state.get("messages", [])
    if not messages:
        return RouteDecision(next_node="finalize")

    last = messages[-1]
    tcs = getattr(last, "tool_calls", None) or []

    for tc in tcs:
        name = tc["name"]

        if name == "general_chat":
            return RouteDecision(
                next_node="general_chat",
                set_node_type="general_chat",
                set_chain_depth=state["chain_depth"] + 1,
            )

        if name == "general_task":
            nt = NODE_TYPES["general_task"]
            entry_idx = nt.available_levels.index(nt.entry_level)
            return RouteDecision(
                next_node="general_task",
                set_node_type="general_task",
                set_chain_depth=0,
                set_level_idx=entry_idx,
            )

        if name == "deep_task":
            nt = NODE_TYPES.get(state["current_node_type"]) or NODE_TYPES["general_task"]
            next_idx = state["current_level_idx"] + 1
            level_idx: int | None = next_idx if next_idx < len(nt.available_levels) else None
            return RouteDecision(
                next_node=state["current_node_type"],
                set_chain_depth=0,
                set_level_idx=level_idx,
            )

        if name == "finish":
            return RouteDecision(next_node="finalize")

    if tcs:
        return RouteDecision(next_node="execute_tools")

    return RouteDecision(next_node="finalize")


def decide_after_tools(state: ExecutionState) -> RouteDecision:
    max_iters = TASK_LEVELS[state["plan"].task_level].max_tool_iterations
    if state.get("tool_iterations", 0) >= max_iters:
        return RouteDecision(next_node="finalize")
    return RouteDecision(next_node=state["current_node_type"])
