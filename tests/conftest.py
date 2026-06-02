"""テスト共通フィクスチャと fakes の再 export。

Fake クラス本体は `tests/fakes/` に領域別 (llm / memory / session / context / tools)
に分割している。互換性のため、既存テストが `from tests.conftest import FakeLLMProvider`
等で参照できるよう再 export する。
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from iris.account.dispatcher import AccountDispatcher
from iris.account.manager import AccountManager
from iris.account.store import AccountStore
from iris.event import EventBus
from iris.kernel.config import Config, ModelConfig, ProactiveConfig
from iris.memory.handler import _MemoryEventHandler
from iris.memory.manager import MemoryManager
from iris.room.dispatcher import _RoomDispatcher
from iris.room.handler import _RoomEventHandler
from iris.room.manager import RoomManager
from iris.room.store import RoomStore
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


@pytest.fixture
def wired_handlers(
    event_bus: EventBus,
    tmp_path: Path,
) -> tuple[AccountDispatcher, _RoomDispatcher, AccountManager, RoomManager]:
    """Memory/Account/Room プラグインの主要ハンドラを event_bus に配線する。"""
    from iris.memory.events.proactive_trigger import ProactiveTrigger
    from iris.memory.sensory.handler import SensoryEventHandler
    from iris.memory.short_term.handler import ShortTermEventHandler

    memory_mgr = MemoryManager()
    memory_mgr.sensory.event_bus = event_bus

    account_store = AccountStore(
        accounts_path=str(tmp_path / "accounts.jsonl"),
        identities_path=str(tmp_path / "identities.jsonl"),
    )
    account_provider = AccountManager(store=account_store, event_bus=event_bus)

    room_store = RoomStore()
    room_provider = RoomManager(store=room_store, event_bus=event_bus, account_manager=account_provider)

    account_dispatcher = AccountDispatcher(account_manager=account_provider)
    room_dispatcher = _RoomDispatcher(room_manager=room_provider, account_manager=account_provider)

    _RoomEventHandler(event_bus=event_bus, store=room_store, room_manager=room_provider)

    sensory_handler = SensoryEventHandler(event_bus, memory_mgr.sensory)
    ShortTermEventHandler(event_bus, memory_mgr.short_term)
    proactive_trigger = ProactiveTrigger(event_bus, room_provider)

    _MemoryEventHandler(
        event_bus=event_bus,
        sensory_handler=sensory_handler,
        proactive_trigger=proactive_trigger,
        proactive_config=None,
    )

    return account_dispatcher, room_dispatcher, account_provider, room_provider
