"""LangGraph routing logic — LLM応答後のノード遷移を決定する。

責務分割:
  routing_decision.py — 純粋な経路決定（state 読み取りのみ）
  state_transition.py — 決定に基づく状態変異（state 書き込みのみ）
  router.py          — 両者を合成し LangGraph 条件付きエッジ関数として公開
"""

from __future__ import annotations

from loguru import logger

from iris.agency.execution.models import ExecutionState
from iris.agency.execution.routing_decision import decide_after_tools, decide_next_route
from iris.agency.execution.state_transition import apply_route_transition


def route_after_llm(state: ExecutionState) -> str:
    decision = decide_next_route(state)
    apply_route_transition(state, decision)
    logger.debug("ROUTE: {} (chain_depth={})", decision.next_node, state["chain_depth"])
    return decision.next_node


def route_after_tools(state: ExecutionState) -> str:
    decision = decide_after_tools(state)
    apply_route_transition(state, decision)
    if decision.next_node == "finalize":
        logger.debug("Tool iteration limit reached")
    return decision.next_node
