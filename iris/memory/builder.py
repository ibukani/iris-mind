"""Memoryレイヤーのコンポーネント組み立て。"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from iris.kernel.manager import PluginManager


def build_memory(manager: PluginManager) -> dict:
    """Memoryレイヤーの全コンポーネントを生成する。"""
    from iris.event.event_bus import EventBus
    from iris.memory.long_term.manager import LongTermMemoryManager
    from iris.memory.long_term.stores import EpisodicStore, SemanticStore
    from iris.memory.long_term.vector_store import VectorStore
    from iris.memory.manager import MemoryManager
    from iris.memory.sensory.manager import SensoryMemoryManager
    from iris.memory.sensory.readiness import ReadinessEvaluator
    from iris.memory.short_term.manager import ShortTermMemoryManager

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

    return {
        "memory": mem,
        "sensory": sensory,
        "short_term": short_term,
        "long_term": long_term,
        "vector_store": vector_store,
        "episodic": episodic,
        "semantic": semantic,
    }
