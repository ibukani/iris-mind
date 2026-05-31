from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage

from iris.agency.execution.models import ExecutionState
from iris.agency.execution.node_type import NODE_TYPES
from iris.agency.execution.routing_decision import RouteDecision, decide_after_tools, decide_next_route
from iris.agency.execution.state_transition import apply_route_transition
from iris.agency.planning.models import Plan


def _chat_plan() -> Plan:
    return Plan(content="", task_level="chat", session_id="s1")


def _normal_plan() -> Plan:
    return Plan(content="hello", task_level="normal", session_id="s1")


def _base_state(plan: Plan, messages: list | None = None) -> ExecutionState:
    return {
        "plan": plan,
        "messages": messages or [],
        "chain_depth": 0,
        "tool_iterations": 0,
        "current_node_type": "general_chat",
        "current_level_idx": 0,
    }


def _routing_msg(name: str) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[{"name": name, "args": {}, "id": f"call_{name}", "type": "tool_call"}],
    )


class TestDecideNextRoute:
    def test_interrupted_routes_to_finalize(self) -> None:
        state = _base_state(_chat_plan())
        state["interrupted"] = True
        assert decide_next_route(state) == RouteDecision(next_node="finalize")

    def test_error_routes_to_finalize(self) -> None:
        state = _base_state(_chat_plan())
        state["error"] = "something went wrong"
        assert decide_next_route(state) == RouteDecision(next_node="finalize")

    def test_empty_messages_routes_to_finalize(self) -> None:
        state = _base_state(_chat_plan())
        assert decide_next_route(state) == RouteDecision(next_node="finalize")

    def test_general_chat_increments_chain_depth(self) -> None:
        state = _base_state(_chat_plan(), [HumanMessage(content="hi")])
        state["chain_depth"] = 3
        state["messages"].append(_routing_msg("general_chat"))

        decision = decide_next_route(state)

        assert decision == RouteDecision(
            next_node="general_chat",
            set_node_type="general_chat",
            set_chain_depth=4,
        )

    def test_general_task_resets_depth_and_sets_entry_level(self) -> None:
        state = _base_state(_chat_plan(), [HumanMessage(content="hi")])
        state["chain_depth"] = 5
        state["messages"].append(_routing_msg("general_task"))

        decision = decide_next_route(state)

        nt = NODE_TYPES["general_task"]
        entry_idx = nt.available_levels.index(nt.entry_level)
        assert decision == RouteDecision(
            next_node="general_task",
            set_node_type="general_task",
            set_chain_depth=0,
            set_level_idx=entry_idx,
        )

    def test_deep_task_upgrades_level(self) -> None:
        state = _base_state(_normal_plan(), [HumanMessage(content="hi")])
        state["current_node_type"] = "general_task"
        state["current_level_idx"] = 0
        state["messages"].append(_routing_msg("deep_task"))

        decision = decide_next_route(state)

        assert decision == RouteDecision(
            next_node="general_task",
            set_chain_depth=0,
            set_level_idx=1,
        )

    def test_deep_task_stays_at_max_level(self) -> None:
        state = _base_state(_normal_plan(), [HumanMessage(content="hi")])
        state["current_node_type"] = "general_task"
        state["current_level_idx"] = 2  # "research" is the last level
        state["messages"].append(_routing_msg("deep_task"))

        decision = decide_next_route(state)

        # level_idx stays unchanged when already at max
        assert decision == RouteDecision(
            next_node="general_task",
            set_chain_depth=0,
            set_level_idx=None,
        )
        assert state["current_level_idx"] == 2  # verify no change

    def test_finish_routes_to_finalize(self) -> None:
        state = _base_state(_chat_plan(), [HumanMessage(content="hi")])
        state["messages"].append(_routing_msg("finish"))

        decision = decide_next_route(state)

        assert decision == RouteDecision(next_node="finalize")

    def test_regular_tool_routes_to_execute(self) -> None:
        state = _base_state(_chat_plan(), [HumanMessage(content="hi")])
        state["messages"].append(
            AIMessage(
                content="",
                tool_calls=[{"name": "web_search", "args": {"q": "test"}, "id": "c1", "type": "tool_call"}],
            ),
        )

        assert decide_next_route(state) == RouteDecision(next_node="execute_tools")

    def test_no_tool_calls_routes_to_finalize(self) -> None:
        state = _base_state(_chat_plan(), [HumanMessage(content="hi")])
        state["messages"].append(AIMessage(content="ok"))
        assert decide_next_route(state) == RouteDecision(next_node="finalize")


class TestDecideAfterTools:
    def test_iteration_limit_reached(self) -> None:
        state = _base_state(_normal_plan())
        state["tool_iterations"] = 5  # normal level max_tool_iterations = 5
        assert decide_after_tools(state) == RouteDecision(next_node="finalize")

    def test_iteration_limit_not_reached(self) -> None:
        state = _base_state(_normal_plan())
        state["tool_iterations"] = 3
        assert decide_after_tools(state) == RouteDecision(next_node="general_chat")

    def test_chat_level_zero_iterations_always_finalize(self) -> None:
        state = _base_state(_chat_plan())
        state["tool_iterations"] = 0  # chat max_tool_iterations = 0 → 0 >= 0 is True
        assert decide_after_tools(state) == RouteDecision(next_node="finalize")


class TestApplyRouteTransition:
    def test_sets_node_type(self) -> None:
        state = _base_state(_chat_plan())
        apply_route_transition(state, RouteDecision(next_node="x", set_node_type="general_task"))
        assert state["current_node_type"] == "general_task"

    def test_sets_chain_depth(self) -> None:
        state = _base_state(_chat_plan())
        state["chain_depth"] = 3
        apply_route_transition(state, RouteDecision(next_node="x", set_chain_depth=0))
        assert state["chain_depth"] == 0

    def test_sets_level_idx(self) -> None:
        state = _base_state(_chat_plan())
        apply_route_transition(state, RouteDecision(next_node="x", set_level_idx=2))
        assert state["current_level_idx"] == 2

    def test_noop_when_all_none(self) -> None:
        state = _base_state(_chat_plan())
        original = dict(state)
        apply_route_transition(state, RouteDecision(next_node="finalize"))
        assert state == original

    def test_partial_update_only_specified_fields(self) -> None:
        state = _base_state(_chat_plan())
        state["chain_depth"] = 5
        state["current_node_type"] = "general_task"
        state["current_level_idx"] = 1
        apply_route_transition(state, RouteDecision(next_node="x", set_chain_depth=0))
        assert state["chain_depth"] == 0
        assert state["current_node_type"] == "general_task"  # unchanged
        assert state["current_level_idx"] == 1  # unchanged


class TestRouteAfterLlmIntegration:
    """route_after_llm が decision + transition の合成として正しく動作することを確認する。

    ここでは router の外部APIではなく、合成された振る舞いを検証する。
    """

    def test_general_chat_side_effects(self) -> None:
        from iris.agency.execution.router import route_after_llm

        state = _base_state(_chat_plan(), [HumanMessage(content="hi")])
        state["chain_depth"] = 2
        state["messages"].append(_routing_msg("general_chat"))

        result = route_after_llm(state)

        assert result == "general_chat"
        assert state["chain_depth"] == 3
        assert state["current_node_type"] == "general_chat"

    def test_general_task_side_effects(self) -> None:
        from iris.agency.execution.router import route_after_llm

        state = _base_state(_chat_plan(), [HumanMessage(content="hi")])
        state["messages"].append(_routing_msg("general_task"))

        result = route_after_llm(state)

        assert result == "general_task"
        assert state["chain_depth"] == 0
        assert state["current_node_type"] == "general_task"
        nt = NODE_TYPES["general_task"]
        assert state["current_level_idx"] == nt.available_levels.index(nt.entry_level)
