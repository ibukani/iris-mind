from __future__ import annotations

from typing import TYPE_CHECKING

from iris.kernel.plugin import PluginCategory, PluginManifest, PluginPhase, PluginProtocol
from iris.memory.builder import MemoryComponents
from iris.memory.long_term.manager import LongTermMemoryManager
from iris.memory.long_term.protocols import (
    AgentsMdStoreProtocol,
    EpisodicStoreProtocol,
    SemanticStoreProtocol,
)
from iris.memory.long_term.stores import (
    AgentsMdStore,
    EpisodicStore,
    SemanticStore,
)
from iris.memory.long_term.vector_store import VectorStore
from iris.memory.manager import MemoryManager
from iris.memory.models import ContentBlock, blocks_text, text_block
from iris.memory.sensory.manager import SensoryMemoryManager
from iris.memory.short_term.manager import ShortTermMemoryManager

if TYPE_CHECKING:
    from iris.kernel.manager import PluginManager

MANIFEST = PluginManifest(
    name="memory",
    version="0.1.0",
    category=PluginCategory.LAYER,
    phase=PluginPhase.LAYER,
    dependencies={"EventBus", "account"},
    provides=["MemoryManager", "SensoryMemoryManager", "ShortTermMemoryManager", "LongTermMemoryManager"],
    description="記憶系（感覚野+海馬+皮質）",
)


class MemoryPlugin(PluginProtocol):
    MANIFEST = MANIFEST

    def init(self, manager: PluginManager) -> None:
        manager.register_manifest(MANIFEST)
        components = self._build_components(manager)
        self._provide_components(manager, components)
        self._wire_event_handler(manager, components)
        from .hooks import register_hooks

        register_hooks(manager)

    def _build_components(self, manager: PluginManager) -> MemoryComponents:
        from iris.memory.builder import build_memory

        return build_memory(manager)

    def _provide_components(self, manager: PluginManager, components: MemoryComponents) -> None:
        manager.provide(MemoryManager, components["memory"])
        manager.provide(SensoryMemoryManager, components["sensory"])
        manager.provide(ShortTermMemoryManager, components["short_term"])
        manager.provide(LongTermMemoryManager, components["long_term"])
        manager.provide(VectorStore, components["vector_store"])

    def _wire_event_handler(self, manager: PluginManager, components: MemoryComponents) -> None:
        from iris.account.handler import _AccountEventHandler
        from iris.event.event_bus import EventBus
        from iris.memory.handler import _MemoryEventHandler

        account_handler = manager.resolve_optional(_AccountEventHandler)

        event_handler = _MemoryEventHandler(
            event_bus=manager.resolve(EventBus),
            sensory=components["sensory"],
            proactive_config=manager.config.proactive,
            short_term=components["short_term"],
            account_handler=account_handler,
        )

        manager.provide(_MemoryEventHandler, event_handler)

    def start(self, manager: PluginManager) -> None:
        pass

    def stop(self, manager: PluginManager) -> None:
        pass


plugin: PluginProtocol = MemoryPlugin()

__all__ = [
    "AgentsMdStore",
    "AgentsMdStoreProtocol",
    "ContentBlock",
    "EpisodicStore",
    "EpisodicStoreProtocol",
    "LongTermMemoryManager",
    "SemanticStore",
    "SemanticStoreProtocol",
    "SensoryMemoryManager",
    "ShortTermMemoryManager",
    "blocks_text",
    "text_block",
]
