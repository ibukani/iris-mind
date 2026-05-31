"""Memoryレイヤーのコンポーネント組み立て。"""

from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict

if TYPE_CHECKING:
    from iris.kernel.manager import PluginManager
    from iris.memory.handler import _MemoryEventHandler
    from iris.memory.long_term.manager import LongTermMemoryManager
    from iris.memory.long_term.stores import EpisodicStore, SemanticStore
    from iris.memory.long_term.vector_store import VectorStore
    from iris.memory.manager import MemoryManager
    from iris.memory.sensory.manager import SensoryMemoryManager
    from iris.memory.short_term.manager import ShortTermMemoryManager


class MemoryComponents(TypedDict):
    memory: MemoryManager
    sensory: SensoryMemoryManager
    short_term: ShortTermMemoryManager
    long_term: LongTermMemoryManager
    vector_store: VectorStore
    episodic: EpisodicStore
    semantic: SemanticStore
    event_handler: _MemoryEventHandler


def build_memory(manager: PluginManager) -> MemoryComponents:
    """Memoryレイヤーの全コンポーネントを生成する。"""
    from iris.memory.long_term.manager import LongTermMemoryManager
    from iris.memory.long_term.stores import EpisodicStore, SemanticStore
    from iris.memory.long_term.vector_store import VectorStore
    from iris.memory.manager import MemoryManager
    from iris.memory.sensory.manager import SensoryMemoryManager
    from iris.memory.sensory.readiness import ReadinessEvaluator
    from iris.memory.short_term.manager import ShortTermMemoryManager

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
    from iris.event.event_bus import EventBus

    event_bus = manager.resolve_optional(EventBus)
    sensory = SensoryMemoryManager(event_bus=event_bus)

    mem = MemoryManager(
        sensory=sensory,
        short_term=short_term,
        long_term=long_term,
    )

    readiness = ReadinessEvaluator(
        min_fragments=config.quasi_sync.response_readiness.tier1_min_fragments,
        question_detect=config.quasi_sync.response_readiness.tier1_question_detect,
        confidence_threshold=config.quasi_sync.response_readiness.confidence_threshold,
        llm=None,
        llm_model_role=config.quasi_sync.response_readiness.llm_model_role,
    )
    sensory.set_readiness_evaluator(readiness)

    # ハンドラのビルドとイベント購読のワイヤリング
    from iris.memory.events.proactive_trigger import ProactiveTrigger
    from iris.memory.handler import _MemoryEventHandler
    from iris.memory.sensory.handler import SensoryEventHandler
    from iris.memory.short_term.handler import ShortTermEventHandler
    from iris.room.manager import RoomManager

    room_provider = manager.resolve_optional(RoomManager)

    sensory_handler = SensoryEventHandler(event_bus, sensory)
    ShortTermEventHandler(event_bus, short_term) if short_term else None
    proactive_trigger = ProactiveTrigger(event_bus, room_provider)

    event_handler = _MemoryEventHandler(
        event_bus=event_bus,
        sensory_handler=sensory_handler,
        proactive_trigger=proactive_trigger,
        proactive_config=config.proactive,
    )

    return {
        "memory": mem,
        "sensory": sensory,
        "short_term": short_term,
        "long_term": long_term,
        "vector_store": vector_store,
        "episodic": episodic,
        "semantic": semantic,
        "event_handler": event_handler,
    }
