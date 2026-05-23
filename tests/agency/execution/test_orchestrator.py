from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from langchain_core.messages import AIMessage, HumanMessage
import pytest

from iris.agency.execution.orchestrator import ExecutionOrchestrator
from iris.agency.execution.state import ExecutionState


@pytest.fixture
def mock_llm() -> AsyncMock:
    mock = AsyncMock()
    mock.set_session_roles_summary = MagicMock()
    return mock


def _make_orchestrator(mock_llm: AsyncMock) -> ExecutionOrchestrator:
    return ExecutionOrchestrator(
        pipeline=mock_llm,
        tool_executor=MagicMock(),
        consolidator=MagicMock(),
        monitor=MagicMock(),
        coordinator=MagicMock(),
        inhibition=MagicMock(),
        event_bus=MagicMock(),
        memory=MagicMock(),
        capability_checker=MagicMock(),
    )


def _chat_short_plan() -> dict:
    """Plan with empty content: SetupNode won't override tools_allowed, uses chat_short path."""
    return {
        "content": "",
        "situation": "proactive",
        "abbreviated": False,
        "model_role": "default",
        "tools_allowed": False,
        "streaming": False,
        "show_thinking": False,
        "max_tokens": 512,
        "session_id": "test-session-001",
        "record_history": True,
        "run_reflexion": False,
        "run_compression": False,
        "temperature": 0.8,
        "silent": False,
    }


def _chat_plan(content: str = "hello") -> dict:
    """Plan with content: SetupNode sets tools_allowed=True, uses chat() path."""
    return {
        "content": content,
        "abbreviated": False,
        "model_role": "default",
        "tools_allowed": True,
        "streaming": True,
        "show_thinking": True,
        "max_tokens": 0,
        "session_id": "test-session-001",
        "record_history": True,
        "run_reflexion": False,
        "run_compression": False,
        "temperature": 0.7,
        "context_hint": "test",
    }


@pytest.mark.anyio
async def test_chat_short_path_propagates_response_text(mock_llm: AsyncMock) -> None:
    """chat_short path (empty content, tools_allowed=False): response_text propagates."""
    mock_llm.chat_short.return_value = "mock short response"
    orch = _make_orchestrator(mock_llm)

    state: ExecutionState = {
        "plan": _chat_short_plan(),
        "messages": [],
        "response_text": "",
        "tool_iterations": 0,
        "interrupted": False,
        "error": None,
        "completed": False,
    }

    result = await orch.ainvoke(state)

    assert result.get("response_text") == "mock short response", (
        f"response_text should be 'mock short response', got {result.get('response_text')!r}"
    )
    assert result.get("completed") is True, "completed should be True"
    mock_llm.chat_short.assert_awaited_once()


@pytest.mark.anyio
async def test_chat_path_propagates_response_text(mock_llm: AsyncMock) -> None:
    """chat() path (content set, tools_allowed=True): response_text propagates."""
    mock_llm.chat.return_value = AIMessage(content="mock assistant response")
    orch = _make_orchestrator(mock_llm)

    state: ExecutionState = {
        "plan": _chat_plan(),
        "messages": [HumanMessage(content="hello")],
        "response_text": "",
        "tool_iterations": 0,
        "interrupted": False,
        "error": None,
        "completed": False,
    }

    result = await orch.ainvoke(state)

    assert result.get("response_text") == "mock assistant response", (
        f"response_text should be 'mock assistant response', got {result.get('response_text')!r}"
    )
    assert result.get("completed") is True, "completed should be True"
    mock_llm.chat.assert_awaited_once()


@pytest.mark.anyio
async def test_empty_chat_short_response(mock_llm: AsyncMock) -> None:
    """Empty LLM response (chat_short): FinalizeNode should still set completed=True."""
    mock_llm.chat_short.return_value = ""
    orch = _make_orchestrator(mock_llm)

    state: ExecutionState = {
        "plan": _chat_short_plan(),
        "messages": [],
        "response_text": "",
        "tool_iterations": 0,
        "interrupted": False,
        "error": None,
        "completed": False,
    }

    result = await orch.ainvoke(state)

    assert result.get("response_text") == ""
    assert result.get("completed") is True, "completed should be True even with empty response"


@pytest.mark.anyio
async def test_messages_accumulate_across_nodes(mock_llm: AsyncMock) -> None:
    """Messages list must grow as nodes append assistant responses."""
    mock_llm.chat_short.return_value = "mock assistant response"
    orch = _make_orchestrator(mock_llm)

    state: ExecutionState = {
        "plan": _chat_short_plan(),
        "messages": [HumanMessage(content="hello")],
        "response_text": "",
        "tool_iterations": 0,
        "interrupted": False,
        "error": None,
        "completed": False,
    }

    result = await orch.ainvoke(state)

    assert len(result["messages"]) >= 1
    assistant_msgs = [m for m in result["messages"] if isinstance(m, AIMessage)]
    assert len(assistant_msgs) == 1
    assert assistant_msgs[0].content == "mock assistant response"


@pytest.mark.anyio
async def test_router_routes_to_finalize_without_tool_calls(mock_llm: AsyncMock) -> None:
    """Without tool calls, router should go directly to finalize."""
    mock_llm.chat.return_value = AIMessage(content="mock assistant response")
    orch = _make_orchestrator(mock_llm)

    state: ExecutionState = {
        "plan": _chat_plan(),
        "messages": [HumanMessage(content="hello")],
        "response_text": "",
        "tool_iterations": 0,
        "interrupted": False,
        "error": None,
        "completed": False,
    }

    result = await orch.ainvoke(state)

    assert result.get("completed") is True
    assert result.get("response_text") == "mock assistant response"
    assert orch._router_after_generate(state) == "finalize"


@pytest.mark.anyio
async def test_error_during_chat_short(mock_llm: AsyncMock) -> None:
    """chat_short exception: should set error and still reach finalize."""
    mock_llm.chat_short.side_effect = RuntimeError("LLM failure")
    orch = _make_orchestrator(mock_llm)

    state: ExecutionState = {
        "plan": _chat_short_plan(),
        "messages": [],
        "response_text": "",
        "tool_iterations": 0,
        "interrupted": False,
        "error": None,
        "completed": False,
    }

    result = await orch.ainvoke(state)

    assert result.get("error") is not None
    assert result.get("completed") is True, "completed should be True even on error"


@pytest.mark.anyio
async def test_error_during_chat(mock_llm: AsyncMock) -> None:
    """chat() exception: should set error and still reach finalize."""
    mock_llm.chat.side_effect = RuntimeError("LLM failure")
    orch = _make_orchestrator(mock_llm)

    state: ExecutionState = {
        "plan": _chat_plan(),
        "messages": [HumanMessage(content="hello")],
        "response_text": "",
        "tool_iterations": 0,
        "interrupted": False,
        "error": None,
        "completed": False,
    }

    result = await orch.ainvoke(state)

    assert result.get("error") is not None
    assert result.get("completed") is True
