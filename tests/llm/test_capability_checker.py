from __future__ import annotations

from iris.kernel.config import ModelConfig
from iris.llm.capability_checker import CapabilityChecker


def _make_checker(
    capabilities: list[str] | None = None,
    performance_tier: str = "balanced",
    role: str = "default",
) -> CapabilityChecker:
    config = ModelConfig(
        models=[{"name": "test", "roles": [role], "capabilities": capabilities, "performance_tier": performance_tier}],  # pyright: ignore[reportArgumentType]
    )
    return CapabilityChecker(config)


def test_supports_tools_from_explicit_capabilities() -> None:
    checker = _make_checker(capabilities=["tools"])
    assert checker.supports_tools() is True


def test_supports_tools_when_not_in_capabilities() -> None:
    checker = _make_checker(capabilities=["thinking"])
    assert checker.supports_tools() is False


def test_supports_tools_capable_tier() -> None:
    checker = _make_checker(capabilities=None, performance_tier="capable")
    assert checker.supports_tools() is True


def test_supports_tools_balanced_tier() -> None:
    checker = _make_checker(capabilities=None, performance_tier="balanced")
    assert checker.supports_tools() is True


def test_supports_tools_fast_tier() -> None:
    checker = _make_checker(capabilities=None, performance_tier="fast")
    assert checker.supports_tools() is False


def test_supports_thinking_from_explicit_capabilities() -> None:
    checker = _make_checker(capabilities=["thinking"])
    assert checker.supports_thinking() is True


def test_supports_thinking_capable_tier() -> None:
    checker = _make_checker(capabilities=None, performance_tier="capable")
    assert checker.supports_thinking() is True


def test_supports_thinking_balanced_tier() -> None:
    checker = _make_checker(capabilities=None, performance_tier="balanced")
    assert checker.supports_thinking() is False


def test_supports_thinking_fast_tier() -> None:
    checker = _make_checker(capabilities=None, performance_tier="fast")
    assert checker.supports_thinking() is False


def test_get_performance_tier() -> None:
    checker = _make_checker(performance_tier="fast")
    assert checker.get_performance_tier() == "fast"
