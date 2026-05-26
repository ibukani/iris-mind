from __future__ import annotations

from typing import TYPE_CHECKING

from iris.event.event_bus import EventBus
from iris.kernel.plugin import PluginCategory, PluginManifest, PluginPhase, PluginProtocol
from iris.memory.long_term.manager import LongTermMemoryManager
from iris.memory.long_term.stores import (
    AgentsMdStore,
    AgentsMdStoreProtocol,
    EpisodicStore,
    EpisodicStoreProtocol,
    SemanticStore,
    SemanticStoreProtocol,
)
from iris.memory.long_term.vector_store import VectorStore
from iris.memory.sensory.manager import SensoryMemoryManager
from iris.memory.sensory.readiness import ReadinessEvaluator
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
        event_bus = manager.resolve(EventBus)
        config = manager.config
        mem_cfg = config.memory

        episodic = EpisodicStore(path=mem_cfg.episodic_path, max_entries=mem_cfg.episodic_max_entries)
        semantic = SemanticStore(
            path=mem_cfg.semantic_path,
            max_entries=mem_cfg.semantic_max_entries,
            vector_db_path=mem_cfg.vector_db_path,
        )
        vector_store = VectorStore(path=mem_cfg.vector_db_path)

        long_term = LongTermMemoryManager(
            episodic=episodic,
            semantic=semantic,
            vector_store=vector_store,
        )
        short_term = ShortTermMemoryManager()
        sensory = SensoryMemoryManager()

        from iris.memory.manager import MemoryManager

        mem = MemoryManager(
            event_bus=event_bus,
            sensory=sensory,
            short_term=short_term,
            long_term=long_term,
            proactive_config=config.proactive,
        )

        readiness = ReadinessEvaluator(
            min_fragments=config.quasi_sync.response_readiness.tier1_min_fragments,
            question_detect=config.quasi_sync.response_readiness.tier1_question_detect,
            confidence_threshold=config.quasi_sync.response_readiness.confidence_threshold,
            llm=None,
            llm_model_role=config.quasi_sync.response_readiness.llm_model_role,
        )
        sensory.set_readiness_evaluator(readiness)

        manager.provide(MemoryManager, mem)
        manager.provide(SensoryMemoryManager, sensory)
        manager.provide(ShortTermMemoryManager, short_term)
        manager.provide(LongTermMemoryManager, long_term)
        manager.provide(VectorStore, vector_store)

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
    "EpisodicStore",
    "EpisodicStoreProtocol",
    "LongTermMemoryManager",
    "SemanticStore",
    "SemanticStoreProtocol",
    "SensoryMemoryManager",
    "ShortTermMemoryManager",
]
