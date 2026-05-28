from __future__ import annotations

from typing import TYPE_CHECKING

from iris.kernel.plugin import PluginCategory, PluginManifest, PluginPhase, PluginProtocol
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
    dependencies={"EventBus"},
    provides=["MemoryManager", "SensoryMemoryManager", "ShortTermMemoryManager", "LongTermMemoryManager"],
    description="記憶系（感覚野+海馬+皮質）",
)


class MemoryPlugin:
    MANIFEST = MANIFEST

    def init(self, manager: PluginManager) -> None:
        manager.register_manifest(MANIFEST)

        from iris.memory.builder import build_memory

        components = build_memory(manager)

        manager.provide(MemoryManager, components["memory"])
        manager.provide(SensoryMemoryManager, components["sensory"])
        manager.provide(ShortTermMemoryManager, components["short_term"])
        manager.provide(LongTermMemoryManager, components["long_term"])
        manager.provide(VectorStore, components["vector_store"])

        from iris.event.event_bus import EventBus
        from iris.memory.handler import _MemoryEventHandler

        _MemoryEventHandler(
            event_bus=manager.resolve(EventBus),
            sensory=components["sensory"],
            proactive_config=manager.config.proactive,
        )

        from .hooks import register_hooks

        register_hooks(manager)

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
