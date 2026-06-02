"""Memoryレイヤーのコンポーネント組み立て。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from iris.kernel.manager import PluginManager
    from iris.memory.archive.store import RawConversationArchiveStore
    from iris.memory.handler import _MemoryEventHandler
    from iris.memory.langmem.pipeline import MemoryPipeline
    from iris.memory.long_term.manager import LongTermMemoryManager
    from iris.memory.long_term.stores import EpisodicStore, SemanticStore
    from iris.memory.long_term.vector_store import VectorStore
    from iris.memory.manager import MemoryManager
    from iris.memory.sensory.manager import SensoryMemoryManager
    from iris.memory.short_term.manager import ShortTermMemoryManager


@dataclass
class MemoryComponents:
    memory: MemoryManager
    sensory: SensoryMemoryManager
    short_term: ShortTermMemoryManager
    long_term: LongTermMemoryManager
    vector_store: VectorStore
    episodic: EpisodicStore
    semantic: SemanticStore
    archive: RawConversationArchiveStore
    pipeline: MemoryPipeline | None
    event_handler: _MemoryEventHandler


def build_memory(manager: PluginManager) -> MemoryComponents:
    """Memoryレイヤーの全コンポーネントを生成する。"""
    from iris.memory.archive.policy import ArchivePolicy
    from iris.memory.archive.store import RawConversationArchiveStore
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

    event_bus: EventBus = manager.resolve_optional(EventBus)  # type: ignore[assignment]
    sensory = SensoryMemoryManager(event_bus=event_bus)

    archive = RawConversationArchiveStore(
        policy=ArchivePolicy(
            archive_dir=mem_cfg.archive_dir,
            max_per_file_bytes=mem_cfg.archive_max_per_file_bytes,
        )
    )

    pipeline = _build_pipeline(manager, archive, long_term, mem_cfg)

    mem = MemoryManager(
        sensory=sensory,
        short_term=short_term,
        long_term=long_term,
        archive=archive,
        pipeline=pipeline,
    )

    readiness = ReadinessEvaluator(
        min_fragments=config.quasi_sync.response_readiness.tier1_min_fragments,
        question_detect=config.quasi_sync.response_readiness.tier1_question_detect,
        confidence_threshold=config.quasi_sync.response_readiness.confidence_threshold,
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

    # アーカイブハンドラ (失敗しても本体フローに影響しない)
    from iris.memory.archive.handler import ArchiveEventHandler

    ArchiveEventHandler(event_bus, archive)

    event_handler = _MemoryEventHandler(
        event_bus=event_bus,
        sensory_handler=sensory_handler,
        proactive_trigger=proactive_trigger,
        proactive_config=config.proactive,
    )

    return MemoryComponents(
        memory=mem,
        sensory=sensory,
        short_term=short_term,
        long_term=long_term,
        vector_store=vector_store,
        episodic=episodic,
        semantic=semantic,
        archive=archive,
        pipeline=pipeline,
        event_handler=event_handler,
    )


def _build_pipeline(
    manager: PluginManager,
    archive: RawConversationArchiveStore,
    long_term: Any,
    mem_cfg: Any,
) -> MemoryPipeline | None:
    """``langmem.enabled`` のときだけ ``MemoryPipeline`` を構築する。"""
    from iris.llm.bridge import LLMBridge
    from iris.memory.consolidation.log_store import MemoryConsolidationLogStore
    from iris.memory.langmem.extractor import LangMemExtractor
    from iris.memory.langmem.pipeline import MemoryPipeline
    from iris.memory.langmem.promotion import PromotionPolicy
    from iris.memory.langmem.stores import MemoryCandidateStore, MemoryExtractionJobStore

    langmem_cfg = mem_cfg.langmem
    if not langmem_cfg.enabled:
        return None
    bridge = manager.resolve_optional(LLMBridge)
    if bridge is None:
        from loguru import logger

        logger.warning("LangMem: enabled but LLMBridge is not available; pipeline disabled.")
        return None
    chat_model = bridge.get_chat_model_for_role(langmem_cfg.model_role)
    if chat_model is None:
        from loguru import logger

        logger.warning("LangMem: no chat model for role={}", langmem_cfg.model_role)
        return None
    candidate_store = MemoryCandidateStore(mem_cfg.candidate_path)
    job_store = MemoryExtractionJobStore(mem_cfg.job_path)
    consolidation_log = MemoryConsolidationLogStore(mem_cfg.consolidation_log_path)
    # ``scope_resolver`` はランタイムのスコープを LangMem 出力に投影する責務。
    # 空文字を返すデフォルトに依存すると候補の scope_account_id/room_id が
    # 全て空文字になり dedup_hash が機能しなくなるため、``MemoryPipeline.run_pass``
    # 側で ``make_job_scope_resolver(account_id, room_id)`` を per-job 注入する
    # 経路を採る。extractor 自体はデフォルトのままで良い。
    extractor = LangMemExtractor(chat_model=chat_model, candidate_store=candidate_store)

    handlers = _build_promotion_handlers(manager, mem_cfg)
    promotion = PromotionPolicy(
        long_term=long_term,
        consolidation_log=consolidation_log,
        min_confidence=langmem_cfg.auto_promote_min_confidence,
        handlers=handlers,
    )
    return MemoryPipeline(
        config=langmem_cfg,
        memory_config=mem_cfg,
        archive=archive,
        job_store=job_store,
        candidate_store=candidate_store,
        extractor=extractor,
        promotion_policy=promotion,
        consolidation_log=consolidation_log,
    )


def _build_promotion_handlers(
    manager: PluginManager,
    mem_cfg: Any,
) -> dict[Any, Any]:
    """PromotionPolicy に登録する handler 群を生成する。

    必須: StylePromotionHandler
    任意: RelationshipPromotionHandler / AppraisalPromotionHandler / PersonaPatchPromotionHandler
    """
    from iris.limbic.relationship import RelationshipManager
    from iris.limbic.stores.appraisal_store import AppraisalEpisodeStore
    from iris.limbic.stores.relationship_store import RelationshipStateStore
    from iris.memory.langmem.handlers import (
        AppraisalPromotionHandler,
        PersonaPatchPromotionHandler,
        RelationshipPromotionHandler,
        StylePromotionHandler,
    )
    from iris.memory.procedural.persona_patch_store import PersonaPatchCandidateStore, PersonaPatchPolicy
    from iris.memory.procedural.style_store import StyleMemoryStore

    style_store = StyleMemoryStore(mem_cfg.style_memory_path)
    handlers: dict[Any, Any] = {
        "style": StylePromotionHandler(style_store=style_store),
    }

    persona_store = PersonaPatchCandidateStore(mem_cfg.persona_patch_path)
    persona_policy = PersonaPatchPolicy(persona_store)
    handlers["persona_patch"] = PersonaPatchPromotionHandler(
        store=persona_store,
        policy=persona_policy,
    )

    relationship_manager = manager.resolve_optional(RelationshipManager)
    if relationship_manager is None:
        from loguru import logger

        logger.debug("builder: RelationshipManager not registered; relationship handler disabled")
    else:
        snapshot_store: RelationshipStateStore | None = None
        try:
            snapshot_store = RelationshipStateStore(mem_cfg.relationship_state_path)
        except Exception:
            snapshot_store = None
        handlers["relationship"] = RelationshipPromotionHandler(
            relationship_manager=relationship_manager,
            snapshot_store=snapshot_store,
        )

    try:
        appraisal_store = AppraisalEpisodeStore(mem_cfg.appraisal_episode_path)
        handlers["appraisal"] = AppraisalPromotionHandler(episode_store=appraisal_store)
    except Exception:
        from loguru import logger

        logger.debug("builder: AppraisalEpisodeStore unavailable; appraisal handler disabled")

    return handlers
