"""LangGraph routing logic — LLM応答後のノード遷移を決定する。"""

from __future__ import annotations

from loguru import logger

from iris.agency.execution.node_types import NODE_TYPES
from iris.agency.execution.state import ExecutionState
from iris.agency.task_level import TASK_LEVELS


def route_after_llm(state: ExecutionState) -> str:
    if state.get("interrupted") or state.get("error"):
        return "finalize"

    messages = state.get("messages", [])
    if not messages:
        return "finalize"

    last = messages[-1]
    tcs = getattr(last, "tool_calls", None) or []

    for tc in tcs:
        name = tc["name"]

        if name == "general_chat":
            state["chain_depth"] += 1
            state["current_node_type"] = "general_chat"
            logger.debug("ROUTE: general_chat (chain depth={})", state["chain_depth"])
            return "general_chat"

        if name == "general_task":
            state["chain_depth"] = 0
            state["current_node_type"] = "general_task"
            nt = NODE_TYPES["general_task"]
            state["current_level_idx"] = nt.available_levels.index(nt.entry_level)
            logger.debug("ROUTE: general_task")
            return "general_task"

        if name == "deep_task":
            state["chain_depth"] = 0
            nt = NODE_TYPES.get(state["current_node_type"]) or NODE_TYPES["general_task"]
            next_idx = state["current_level_idx"] + 1
            if next_idx < len(nt.available_levels):
                state["current_level_idx"] = next_idx
                logger.debug(
                    "ROUTE: deep_task level={}",
                    nt.available_levels[state["current_level_idx"]],
                )
            return state["current_node_type"]

        if name == "finish":
            logger.debug("ROUTE: finish")
            return "finalize"

    if tcs:
        return "execute_tools"

    return "finalize"


def route_after_tools(state: ExecutionState) -> str:
    max_iters = TASK_LEVELS[state["plan"].task_level].max_tool_iterations
    if state.get("tool_iterations", 0) >= max_iters:
        logger.debug("Tool iteration limit reached ({})", max_iters)
        return "finalize"
    return state["current_node_type"]
