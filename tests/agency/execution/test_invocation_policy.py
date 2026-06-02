from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from iris.agency.execution.llm.invocation_policy import ModelInvocationPolicy


@pytest.fixture
def checker_with_tools() -> MagicMock:
    mock = MagicMock()
    mock.supports_tools.return_value = True
    mock.supports_thinking.return_value = True
    return mock


@pytest.fixture
def checker_no_tools() -> MagicMock:
    mock = MagicMock()
    mock.supports_tools.return_value = False
    mock.supports_thinking.return_value = False
    return mock


class TestResolveTools:
    def test_returns_tools_when_supported(self, checker_with_tools: MagicMock) -> None:
        policy = ModelInvocationPolicy(checker_with_tools)
        tools = [{"type": "function", "function": {"name": "test"}}]
        result = policy.resolve_tools(tools, "medium")
        assert result == tools

    def test_returns_none_when_not_supported(self, checker_no_tools: MagicMock) -> None:
        policy = ModelInvocationPolicy(checker_no_tools)
        tools = [{"type": "function", "function": {"name": "test"}}]
        result = policy.resolve_tools(tools, "low")
        assert result is None

    def test_returns_none_when_no_checker(self) -> None:
        policy = ModelInvocationPolicy(None)
        tools = [{"type": "function", "function": {"name": "test"}}]
        result = policy.resolve_tools(tools, "medium")
        assert result == tools

    def test_returns_none_for_empty_input(self, checker_with_tools: MagicMock) -> None:
        policy = ModelInvocationPolicy(checker_with_tools)
        assert policy.resolve_tools([], "medium") is None
        assert policy.resolve_tools(None, "medium") is None


class TestResolveThinking:
    def test_returns_true_when_supported(self, checker_with_tools: MagicMock) -> None:
        policy = ModelInvocationPolicy(checker_with_tools)
        assert policy.resolve_thinking(True, "medium") is True

    def test_returns_false_when_not_supported(self, checker_no_tools: MagicMock) -> None:
        policy = ModelInvocationPolicy(checker_no_tools)
        assert policy.resolve_thinking(True, "low") is False

    def test_returns_false_when_not_requested(self, checker_with_tools: MagicMock) -> None:
        policy = ModelInvocationPolicy(checker_with_tools)
        assert policy.resolve_thinking(False, "medium") is False

    def test_returns_false_when_no_checker_and_not_requested(self) -> None:
        policy = ModelInvocationPolicy(None)
        assert policy.resolve_thinking(False, "medium") is False

    def test_returns_true_when_no_checker_and_requested(self) -> None:
        policy = ModelInvocationPolicy(None)
        assert policy.resolve_thinking(True, "medium") is True


class TestResolveTemperature:
    def test_explicit_wins(self) -> None:
        policy = ModelInvocationPolicy(None)
        result = policy.resolve_temperature(0.0, 0.85, 0.5, 0.7)
        assert result == 0.0

    def test_level_fallback(self) -> None:
        policy = ModelInvocationPolicy(None)
        result = policy.resolve_temperature(None, 0.85, 0.5, 0.7)
        assert result == 0.85

    def test_modulation_fallback(self) -> None:
        policy = ModelInvocationPolicy(None)
        result = policy.resolve_temperature(None, None, 0.5, 0.7)
        assert result == 0.5

    def test_config_fallback(self) -> None:
        policy = ModelInvocationPolicy(None)
        result = policy.resolve_temperature(None, None, None, 0.7)
        assert result == 0.7
