"""テスト共通フィクスチャと fakes の再 export。

Fake クラス本体は `tests/fakes/` に領域別 (llm / memory / session / context / tools)
に分割している。互換性のため、既存テストが `from tests.conftest import FakeLLMProvider`
等で参照できるよう再 export する。
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from iris.event import EventBus
from iris.kernel.config import Config, ModelConfig, ProactiveConfig
from tests.fakes import (
    FakeAgentsMdStore,
    FakeContextManager,
    FakeEpisodicStore,
    FakeLLMProvider,
    FakeMemoryManager,
    FakeSemanticStore,
    FakeSessionManager,
    FakeToolExecutionEngine,
    FakeVectorStore,
)

__all__ = [
    "FakeAgentsMdStore",
    "FakeContextManager",
    "FakeEpisodicStore",
    "FakeLLMProvider",
    "FakeMemoryManager",
    "FakeSemanticStore",
    "FakeSessionManager",
    "FakeToolExecutionEngine",
    "FakeVectorStore",
]


# ── Fixtures ──────────────────────────────────────────────────


@pytest.fixture
def event_bus() -> EventBus:
    return EventBus()


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
def minimal_config() -> Config:
    return Config(
        model=ModelConfig(
            models=[{"name": "test-model", "roles": ["default"]}],  # pyright: ignore[reportArgumentType]
        ),
    )


@pytest.fixture
def proactive_config() -> ProactiveConfig:
    return ProactiveConfig(
        check_interval_sec=5.0,
        min_interval_sec=60.0,
        max_interval_sec=600.0,
        speak_threshold=0.3,
    )


@pytest.fixture
def mock_time_provider() -> Callable[[], float]:
    """Returns a time provider that starts at 1000.0 and increments by 1 each call."""
    t: float = 1000.0

    def _time() -> float:
        nonlocal t
        current = t
        t += 1.0
        return current

    return _time
