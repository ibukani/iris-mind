"""Legacy test fixtures for Plugin/EventBus-centered tests.

These fixtures import legacy ``iris.*`` modules at call time.  They must only
be used by tests under ``tests/legacy/`` or by legacy test directories that
still depend on Plugin/EventBus runtime modules.

Target tests must NOT use these fixtures.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest

if TYPE_CHECKING:
    from iris.account.dispatcher import AccountDispatcher
    from iris.account.manager import AccountManager
    from iris.event import EventBus
    from iris.kernel.config import Config, ProactiveConfig
    from iris.room.dispatcher import _RoomDispatcher
    from iris.room.manager import RoomManager


def _legacy_import[T](value: T) -> T:
    """Return a lazily imported legacy object.

    This helper makes the intentional boundary visible in fixture bodies and
    keeps root conftest collection free from legacy imports.
    """
    return value


@pytest.fixture
def event_bus() -> EventBus:
    from iris.event import EventBus

    return _legacy_import(EventBus)()


@pytest.fixture
def minimal_config() -> Config:
    from iris.kernel.config import Config, ModelConfig

    config_cls = _legacy_import(Config)
    model_config_cls = _legacy_import(ModelConfig)
    return config_cls(
        model=model_config_cls(
            models=[{"name": "test-model", "roles": ["default"]}],  # pyright: ignore[reportArgumentType]
        ),
    )


@pytest.fixture
def proactive_config() -> ProactiveConfig:
    from iris.kernel.config import ProactiveConfig

    config_cls = _legacy_import(ProactiveConfig)
    return config_cls(
        check_interval_sec=5.0,
        min_interval_sec=60.0,
        max_interval_sec=600.0,
        speak_threshold=0.3,
    )


@pytest.fixture
def wired_handlers(
    event_bus: EventBus,
    tmp_path: Path,
) -> tuple[AccountDispatcher, _RoomDispatcher, AccountManager, RoomManager]:
    """Wire the main legacy Memory/Account/Room handlers to an EventBus."""
    from iris.account.dispatcher import AccountDispatcher
    from iris.account.manager import AccountManager
    from iris.account.store import AccountStore
    from iris.memory.events.proactive_trigger import ProactiveTrigger
    from iris.memory.handler import _MemoryEventHandler
    from iris.memory.manager import MemoryManager
    from iris.memory.sensory.handler import SensoryEventHandler
    from iris.memory.short_term.handler import ShortTermEventHandler
    from iris.room.dispatcher import _RoomDispatcher
    from iris.room.handler import _RoomEventHandler
    from iris.room.manager import RoomManager
    from iris.room.store import RoomStore

    memory_mgr = _legacy_import(MemoryManager)()
    memory_mgr.sensory.event_bus = event_bus

    account_store = _legacy_import(AccountStore)(
        accounts_path=str(tmp_path / "accounts.jsonl"),
        identities_path=str(tmp_path / "identities.jsonl"),
    )
    account_provider = _legacy_import(AccountManager)(store=account_store, event_bus=event_bus)

    room_store = _legacy_import(RoomStore)()
    room_provider = _legacy_import(RoomManager)(
        store=room_store,
        event_bus=event_bus,
        account_manager=account_provider,
    )

    account_dispatcher = _legacy_import(AccountDispatcher)(account_manager=account_provider)
    room_dispatcher = _legacy_import(_RoomDispatcher)(room_manager=room_provider, account_manager=account_provider)

    _legacy_import(_RoomEventHandler)(event_bus=event_bus, store=room_store, room_manager=room_provider)

    sensory_handler = _legacy_import(SensoryEventHandler)(event_bus, memory_mgr.sensory)
    _legacy_import(ShortTermEventHandler)(event_bus, memory_mgr.short_term)
    proactive_trigger = _legacy_import(ProactiveTrigger)(event_bus, room_provider)

    _legacy_import(_MemoryEventHandler)(
        event_bus=event_bus,
        sensory_handler=sensory_handler,
        proactive_trigger=proactive_trigger,
        proactive_config=None,
    )

    return cast(
        "tuple[AccountDispatcher, _RoomDispatcher, AccountManager, RoomManager]",
        (account_dispatcher, room_dispatcher, account_provider, room_provider),
    )
