"""Shared pytest fixtures.

The v1.2.1 target test suite must be collectible without importing legacy
Plugin/EventBus runtime modules.  Keep this file lightweight: re-export fakes
at module import time only.

Legacy fixtures (``event_bus``, ``minimal_config``, ``proactive_config``,
``wired_handlers``) have moved to ``tests/legacy/conftest.py``.  They are
available to legacy tests via pytest's conftest inheritance, but target tests
must not depend on them.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from tests.fakes.context import FakeContextManager
from tests.fakes.llm import FakeLLMProvider
from tests.fakes.memory import (
    FakeAgentsMdStore,
    FakeEpisodicStore,
    FakeMemoryManager,
    FakeSemanticStore,
    FakeVectorStore,
)
from tests.fakes.tools import FakeToolExecutionEngine

__all__ = [
    "FakeAgentsMdStore",
    "FakeContextManager",
    "FakeEpisodicStore",
    "FakeLLMProvider",
    "FakeMemoryManager",
    "FakeSemanticStore",
    "FakeToolExecutionEngine",
    "FakeVectorStore",
]


def __getattr__(name: str) -> Any:
    if name == "FakeSessionManager":
        from tests.fakes.session import FakeSessionManager

        return FakeSessionManager
    if name == "FakeSessionInfo":
        from tests.fakes.session import FakeSessionInfo

        return FakeSessionInfo
    raise AttributeError(name)


# -- Target-safe fake fixtures --


@pytest.fixture
def fake_llm() -> FakeLLMProvider:
    return FakeLLMProvider()


@pytest.fixture
def fake_episodic() -> FakeEpisodicStore:
    return FakeEpisodicStore()


@pytest.fixture
def fake_semantic() -> FakeSemanticStore:
    return FakeSemanticStore()


@pytest.fixture
def fake_vector() -> FakeVectorStore:
    return FakeVectorStore()


@pytest.fixture
def fake_memory() -> FakeMemoryManager:
    return FakeMemoryManager()


@pytest.fixture
def fake_agents_md() -> FakeAgentsMdStore:
    return FakeAgentsMdStore()


@pytest.fixture
def fake_context_mgr() -> FakeContextManager:
    return FakeContextManager()


@pytest.fixture
def fake_tool_exec() -> FakeToolExecutionEngine:
    return FakeToolExecutionEngine()


@pytest.fixture
def mock_time_provider() -> Callable[[], float]:
    """Return a time provider that starts at 1000.0 and increments by 1 each call."""
    t: float = 1000.0

    def _time() -> float:
        nonlocal t
        current = t
        t += 1.0
        return current

    return _time
