"""Test fakes (Fake* クラス群) を領域別に分割して再利用する。

pytest conftest.py から再 export して、既存テストの互換性を維持する。
"""

from tests.fakes.context import FakeContextManager
from tests.fakes.llm import FakeLLMProvider
from tests.fakes.memory import (
    FakeAgentsMdStore,
    FakeEpisodicStore,
    FakeMemoryManager,
    FakeSemanticStore,
    FakeVectorStore,
)
from tests.fakes.session import FakeSessionInfo, FakeSessionManager
from tests.fakes.tools import FakeCapabilityRegistry, FakeToolExecutionEngine

__all__ = [
    "FakeAgentsMdStore",
    "FakeCapabilityRegistry",
    "FakeContextManager",
    "FakeEpisodicStore",
    "FakeLLMProvider",
    "FakeMemoryManager",
    "FakeSemanticStore",
    "FakeSessionInfo",
    "FakeSessionManager",
    "FakeToolExecutionEngine",
    "FakeVectorStore",
]
