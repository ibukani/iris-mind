from __future__ import annotations

from tests.conftest import FakeToolExecutionEngine


def test_execute_all_empty_context() -> None:
    engine = FakeToolExecutionEngine()
    results = engine.execute_all([])
    assert results == []


def test_execute_all_no_tool_calls() -> None:
    engine = FakeToolExecutionEngine()
    ctx = [{"role": "user", "content": "hi"}]
    results = engine.execute_all(ctx)
    assert results == []


def test_execute_all_with_tool_calls() -> None:
    engine = FakeToolExecutionEngine()
    ctx = [
        {"role": "user", "content": "list files"},
        {
            "role": "assistant",
            "content": "Let me check",
            "tool_calls": [{"id": "1", "type": "function", "function": {"name": "list_files", "arguments": "{}"}}],
        },
    ]
    results = engine.execute_all(ctx)
    assert len(results) == 1
    assert results[0] == ("list_files", "ok")
    assert len(ctx) == 3
    assert ctx[2]["role"] == "tool"


def test_execute_all_multiple_tool_calls() -> None:
    engine = FakeToolExecutionEngine()
    ctx = [
        {"role": "user", "content": "do two things"},
        {
            "role": "assistant",
            "content": "OK",
            "tool_calls": [
                {"id": "1", "type": "function", "function": {"name": "read_file", "arguments": '{"path":"a"}'}},
                {"id": "2", "type": "function", "function": {"name": "read_file", "arguments": '{"path":"b"}'}},
            ],
        },
    ]
    results = engine.execute_all(ctx)
    assert len(results) == 2


def test_should_follow_up_returns_false() -> None:
    engine = FakeToolExecutionEngine()
    assert engine.should_follow_up([]) is False
