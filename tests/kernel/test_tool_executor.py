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
    assert results[0] == ("list_files", "ok", False)
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


def test_all_side_effects_empty() -> None:
    engine = FakeToolExecutionEngine()
    assert engine.all_side_effects([]) is False


def test_all_side_effects_true() -> None:
    engine = FakeToolExecutionEngine()
    assert engine.all_side_effects([("a", "ok", True)]) is True


def test_all_side_effects_false() -> None:
    engine = FakeToolExecutionEngine()
    assert engine.all_side_effects([("a", "ok", False)]) is False
    assert engine.all_side_effects([("a", "ok", True), ("b", "ok", False)]) is False


def test_side_effect_tool_does_not_add_to_ctx() -> None:
    engine = FakeToolExecutionEngine()
    engine.registry._side_effects.add("noop_tool")
    ctx = [
        {
            "role": "assistant",
            "tool_calls": [{"id": "1", "type": "function", "function": {"name": "noop_tool", "arguments": "{}"}}],
        },
    ]
    results = engine.execute_all(ctx)
    assert len(results) == 1
    assert results[0] == ("noop_tool", "ok", True)
    assert len(ctx) == 1


def test_mixed_side_effect_and_normal() -> None:
    engine = FakeToolExecutionEngine()
    engine.registry._side_effects.add("side_tool")
    ctx = [
        {
            "role": "assistant",
            "tool_calls": [
                {"id": "1", "type": "function", "function": {"name": "side_tool", "arguments": "{}"}},
                {"id": "2", "type": "function", "function": {"name": "normal_tool", "arguments": "{}"}},
            ],
        },
    ]
    results = engine.execute_all(ctx)
    assert len(results) == 2
    assert results[0] == ("side_tool", "ok", True)
    assert results[1] == ("normal_tool", "ok", False)
    assert len(ctx) == 2
    assert ctx[1]["role"] == "tool"
