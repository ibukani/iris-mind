from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from langchain_core.messages import AIMessage, HumanMessage
import pytest

from iris.agency import ExecutionOrchestrator, ExecutionState, Plan
from iris.agency.execution.router import route_after_llm

pytestmark = pytest.mark.legacy


@pytest.fixture
def mock_llm() -> AsyncMock:
    return AsyncMock()


def _make_orchestrator(mock_llm: AsyncMock) -> ExecutionOrchestrator:
    return ExecutionOrchestrator(
        pipeline=mock_llm,
        tool_executor=MagicMock(),
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
        "chain_depth": 0,
        "tool_iterations": 0,
        "current_node_type": "general_chat",
        "current_level_idx": 0,
    }


@pytest.mark.anyio
@pytest.mark.parametrize(
    "plan_factory",
    [_chat_plan, _normal_plan],
    ids=["chat", "normal"],
)
async def test_chat_path_propagates_response_text(mock_llm: AsyncMock, plan_factory) -> None:
    mock_llm.chat.return_value = AIMessage(content="mock assistant response")
    orch = _make_orchestrator(mock_llm)

    state = _base_state(plan_factory(), [HumanMessage(content="hello")])

    result = await orch.ainvoke(state)

    assert result.get("response_text") == "mock assistant response"
    assert result.get("completed") is True
    mock_llm.chat.assert_awaited_once()


@pytest.mark.anyio
async def test_empty_chat_response(mock_llm: AsyncMock) -> None:
    mock_llm.chat.return_value = AIMessage(content="")
    orch = _make_orchestrator(mock_llm)

    state = _base_state(_chat_plan(), [HumanMessage(content="hello")])

    result = await orch.ainvoke(state)

    assert result.get("response_text") == ""
    assert result.get("completed") is True
    mock_llm.chat.assert_awaited_once()


@pytest.mark.anyio
async def test_messages_accumulate_across_nodes(mock_llm: AsyncMock) -> None:
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
    mock_llm.chat.return_value = AIMessage(content="mock assistant response")
    orch = _make_orchestrator(mock_llm)

    state = _base_state(_chat_plan(), [HumanMessage(content="hello")])

    result = await orch.ainvoke(state)
    assert result.get("completed") is True
    assert result.get("response_text") == "mock assistant response"
    assert route_after_llm(state) == "finalize"


@pytest.mark.anyio
async def test_error_during_chat(mock_llm: AsyncMock) -> None:
    mock_llm.chat.side_effect = RuntimeError("LLM failure")
    orch = _make_orchestrator(mock_llm)

    state = _base_state(_chat_plan(), [HumanMessage(content="hello")])

    result = await orch.ainvoke(state)

    assert result.get("error") is not None
    assert result.get("completed") is True


@pytest.mark.anyio
async def test_interrupted_state(mock_llm: AsyncMock) -> None:
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


@pytest.mark.anyio
async def test_full_graph_with_general_task_routing(mock_llm: AsyncMock) -> None:
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
