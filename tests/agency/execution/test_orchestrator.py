from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from langchain_core.messages import AIMessage, HumanMessage
import pytest

from iris.agency import ExecutionOrchestrator, ExecutionState, Plan


@pytest.fixture
def mock_llm() -> AsyncMock:
    mock = AsyncMock()
    mock.set_session_roles_summary = MagicMock()
    return mock


def _make_orchestrator(mock_llm: AsyncMock) -> ExecutionOrchestrator:
    return ExecutionOrchestrator(
        pipeline=mock_llm,
        tool_executor=MagicMock(),
        capability_checker=MagicMock(),
        event_bus=MagicMock(),
        memory=MagicMock(),
    )


def _chat_plan(content: str = "", is_silent: bool = False) -> Plan:
    return Plan(
        content=content,
        task_level="chat",
        silent=is_silent,
        session_id="test-session-001",
    )


def _normal_plan(content: str = "hello") -> Plan:
    return Plan(
        content=content,
        task_level="normal",
        silent=False,
        context_hint="test",
        session_id="test-session-001",
    )


def _base_state(plan: dict, messages: list | None = None) -> ExecutionState:
    return {
        "plan": plan,
        "messages": messages or [],
        "response_text": "",
        "tool_iterations": 0,
        "interrupted": False,
        "error": None,
        "completed": False,
        "current_node_type": "general_chat",
        "current_level_idx": 0,
        "chain_depth": 0,
    }


@pytest.mark.anyio
async def test_chat_path_propagates_response_text(mock_llm: AsyncMock) -> None:
    """chat() path with response text propagates through graph."""
    mock_llm.chat.return_value = AIMessage(content="mock assistant response")
    orch = _make_orchestrator(mock_llm)

    state = _base_state(_chat_plan(), [HumanMessage(content="hello")])

    result = await orch.ainvoke(state)

    assert result.get("response_text") == "mock assistant response", (
        f"response_text should be 'mock assistant response', got {result.get('response_text')!r}"
    )
    assert result.get("completed") is True, "completed should be True"
    mock_llm.chat.assert_awaited_once()


@pytest.mark.anyio
async def test_normal_path_propagates_response_text(mock_llm: AsyncMock) -> None:
    """normal task_level path propagates response correctly."""
    mock_llm.chat.return_value = AIMessage(content="mock assistant response")
    orch = _make_orchestrator(mock_llm)

    state = _base_state(_normal_plan(), [HumanMessage(content="hello")])

    result = await orch.ainvoke(state)

    assert result.get("response_text") == "mock assistant response"
    assert result.get("completed") is True
    mock_llm.chat.assert_awaited_once()


@pytest.mark.anyio
async def test_empty_chat_response(mock_llm: AsyncMock) -> None:
    """Empty LLM response should still set completed=True."""
    mock_llm.chat.return_value = AIMessage(content="")
    orch = _make_orchestrator(mock_llm)

    state = _base_state(_chat_plan(), [HumanMessage(content="hello")])

    result = await orch.ainvoke(state)

    assert result.get("response_text") == ""
    assert result.get("completed") is True


@pytest.mark.anyio
async def test_messages_accumulate_across_nodes(mock_llm: AsyncMock) -> None:
    """Messages list must grow as nodes append assistant responses."""
    mock_llm.chat.return_value = AIMessage(content="mock assistant response")
    orch = _make_orchestrator(mock_llm)

    state = _base_state(_chat_plan(), [HumanMessage(content="hello")])

    result = await orch.ainvoke(state)

    assert len(result["messages"]) >= 2
    assistant_msgs = [m for m in result["messages"] if isinstance(m, AIMessage)]
    assert len(assistant_msgs) == 1
    assert assistant_msgs[0].content == "mock assistant response"


@pytest.mark.anyio
async def test_router_routes_to_finalize_without_tool_calls(mock_llm: AsyncMock) -> None:
    """Without tool calls, router should go directly to finalize."""
    mock_llm.chat.return_value = AIMessage(content="mock assistant response")
    orch = _make_orchestrator(mock_llm)

    state = _base_state(_chat_plan(), [HumanMessage(content="hello")])

    result = await orch.ainvoke(state)

    assert result.get("completed") is True
    assert result.get("response_text") == "mock assistant response"
    assert orch._route_after_llm(state) == "finalize"


@pytest.mark.anyio
async def test_error_during_chat(mock_llm: AsyncMock) -> None:
    """Exception during chat: should set error and still reach finalize."""
    mock_llm.chat.side_effect = RuntimeError("LLM failure")
    orch = _make_orchestrator(mock_llm)

    state = _base_state(_chat_plan(), [HumanMessage(content="hello")])

    result = await orch.ainvoke(state)

    assert result.get("error") is not None
    assert result.get("completed") is True


@pytest.mark.anyio
async def test_interrupted_state(mock_llm: AsyncMock) -> None:
    """Interrupted state should skip LLM call and go to finalize."""
    orch = _make_orchestrator(mock_llm)

    state = _base_state(_chat_plan(), [HumanMessage(content="hello")])
    state["interrupted"] = True

    result = await orch.ainvoke(state)

    assert result.get("completed") is True
    mock_llm.chat.assert_not_awaited()


def _routing_msg(name: str) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[{"name": name, "args": {}, "id": f"call_{name}", "type": "tool_call"}],
    )


def test_route_after_llm_routes_to_general_task(mock_llm: AsyncMock) -> None:
    """general_chat routing tool switches node_type to general_task."""
    orch = _make_orchestrator(mock_llm)
    state = _base_state(_chat_plan(), [HumanMessage(content="hello")])
    state["messages"].append(_routing_msg("general_task"))

    route = orch._route_after_llm(state)

    assert route == "general_task"
    assert state["current_node_type"] == "general_task"
    assert state["chain_depth"] == 0


def test_route_after_llm_deep_task_upgrades_level(mock_llm: AsyncMock) -> None:
    """deep_task routing tool upgrades current_level_idx by 1."""
    orch = _make_orchestrator(mock_llm)
    state = _base_state(_chat_plan(), [HumanMessage(content="hello")])
    state["current_node_type"] = "general_task"
    state["current_level_idx"] = 0
    state["messages"].append(_routing_msg("deep_task"))

    route = orch._route_after_llm(state)

    assert route == "general_task"
    assert state["current_level_idx"] == 1


def test_route_after_llm_finish_routes_to_finalize(mock_llm: AsyncMock) -> None:
    """finish routing tool sends execution to finalize."""
    orch = _make_orchestrator(mock_llm)
    state = _base_state(_chat_plan(), [HumanMessage(content="hello")])
    state["messages"].append(_routing_msg("finish"))

    route = orch._route_after_llm(state)

    assert route == "finalize"


def test_route_after_llm_regular_tool_routes_to_execute(mock_llm: AsyncMock) -> None:
    """Non-routing tool_calls should go to execute_tools."""
    orch = _make_orchestrator(mock_llm)
    state = _base_state(_chat_plan(), [HumanMessage(content="hello")])
    state["messages"].append(
        AIMessage(
            content="",
            tool_calls=[{"name": "web_search", "args": {"q": "test"}, "id": "call_ws", "type": "tool_call"}],
        ),
    )

    route = orch._route_after_llm(state)

    assert route == "execute_tools"


def test_route_after_llm_no_tool_calls_routes_to_finalize(mock_llm: AsyncMock) -> None:
    """No tool_calls means direct to finalize."""
    orch = _make_orchestrator(mock_llm)
    state = _base_state(_chat_plan(), [HumanMessage(content="hello")])
    state["messages"].append(AIMessage(content="ok"))

    route = orch._route_after_llm(state)

    assert route == "finalize"


def test_route_after_llm_general_chat_increments_chain_depth(mock_llm: AsyncMock) -> None:
    """general_chat routing tool increments chain_depth."""
    orch = _make_orchestrator(mock_llm)
    state = _base_state(_chat_plan(), [HumanMessage(content="hello")])
    state["chain_depth"] = 3
    state["messages"].append(_routing_msg("general_chat"))

    route = orch._route_after_llm(state)

    assert route == "general_chat"
    assert state["chain_depth"] == 4


@pytest.mark.anyio
async def test_full_graph_with_general_task_routing(mock_llm: AsyncMock) -> None:
    """general_chat→general_task→response flows correctly end-to-end."""
    mock_llm.chat.side_effect = [
        _routing_msg("general_task"),
        AIMessage(content="task mode response"),
    ]
    orch = _make_orchestrator(mock_llm)

    plan = _normal_plan()
    state = _base_state(plan, [HumanMessage(content="hello")])

    result = await orch.ainvoke(state)

    assert result.get("response_text") == "task mode response"
    assert result.get("completed") is True
    assert mock_llm.chat.await_count == 2
