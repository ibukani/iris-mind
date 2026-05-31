from __future__ import annotations

from iris.agency.execution.models import ExecutionState
from iris.agency.execution.routing_decision import RouteDecision


def apply_route_transition(state: ExecutionState, decision: RouteDecision) -> None:
    if decision.set_node_type is not None:
        state["current_node_type"] = decision.set_node_type
    if decision.set_chain_depth is not None:
        state["chain_depth"] = decision.set_chain_depth
    if decision.set_level_idx is not None:
        state["current_level_idx"] = decision.set_level_idx
