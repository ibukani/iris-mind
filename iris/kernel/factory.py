from __future__ import annotations

from dataclasses import dataclass
import logging

from iris.agency.bus import InternalBus
from iris.agency.execution.inhibition import InhibitionController
from iris.agency.execution.manager import ExecutionManager
from iris.agency.execution.monitor import OutputMonitor
from iris.agency.execution.pipeline import LLMPipeline
from iris.agency.execution.tool_executor import ToolExecutionEngine
from iris.agency.manager import AgencyManager
from iris.agency.planning.manager import PlanningManager
from iris.agency.planning.scoring import ProactiveScoring
from iris.event.event_bus import EventBus
from iris.io.manager import IOManager
from iris.io.session.manager import SessionConfig, SessionManager
from iris.io.transport.tcp_listener import TcpListener
from iris.kernel.commands.handler import CommandHandler
from iris.limbic.emotional_memory import EmotionalMemory
from iris.limbic.manager import LimbicManager
from iris.llm.capability_checker import CapabilityChecker
from iris.llm.context_window import LLMContextWindowManager
from iris.llm.llm_bridge import LLMBridge
from iris.llm.tokenizer_manager import TokenizerManager
from iris.memory.hippocampal.manager import HippocampalManager
from iris.memory.hippocampal.reflexion import Reflexion
from iris.memory.long_term.manager import LongTermMemoryManager
from iris.memory.long_term.stores import AgentsMdStore, EpisodicStore, SemanticStore
from iris.memory.long_term.vector_store import VectorStore
from iris.memory.manager import MemoryManager
from iris.memory.personality.big_five import BigFiveProfile
from iris.memory.personality.persona_data import PersonaData
from iris.memory.personality.persona_profile import PersonaProfile
from iris.memory.personality.personality import Personality
from iris.memory.sensory.manager import SensoryMemoryManager
from iris.memory.sensory.readiness import ReadinessEvaluator
from iris.memory.short_term.manager import ShortTermMemoryManager
from iris.tools.registry import ToolRegistry

from .config import Config
from .manager import KernelManager

logger = logging.getLogger(__name__)


@dataclass
class KernelContext:
    event_bus: EventBus
    kernel: KernelManager
    io: IOManager
    limbic: LimbicManager
    memory: MemoryManager
    agency: AgencyManager
    cmd_handler: CommandHandler
    tcp_listener: TcpListener
    session_mgr: SessionManager
    shutdown_requested: bool = False


class KernelFactory:
    @staticmethod
    def build(config: Config) -> KernelContext:
        """設定に基づいて Iris の全層を構築し、KernelContext で統合する。

        ビルド順序：
        1. InfraProvider: EventBus, IO, TCP
        2. StorageLayer: ファイルベース記憶（Episodic, Semantic, Agents MD）
        3. MemoryLayer: ベクトルストア、人格、感覚バッファ
        4. LLMLayer: プロバイダ、ブリッジ、コンテキスト管理
        5. AgencyLayer: 計画・実行エンジン（PlanningManager, ExecutionManager）
        6. CommandHandler: シャットダウンなどのコマンド処理
        7. KernelProcess: 全層のイベントループ管理

        Args:
            config: Config インスタンス。config.yaml から model_config, proactive, io 等を読む。

        Returns:
            KernelContext: 構築完了した全層へのアクセスポイント集約。

        Raises:
            LLMAvailabilityError: 指定プロバイダが利用不可な場合。
        """
        # ============================================================
        # Phase 1: インフラ基盤 (EventBus, IO)
        # ============================================================
        event_bus = EventBus()
        session_mgr = SessionManager(config=SessionConfig(**config.session.model_dump()))
        tcp_listener = TcpListener(session_manager=session_mgr)

        io_mgr = IOManager(
            event_bus=event_bus,
            session_manager=session_mgr,
            tcp_listener=tcp_listener,
        )

        # ============================================================
        # Phase 2: 記憶ストア構築（MemoryManager / EmotionalMemory で共用）
        # ============================================================
        mem_cfg = config.memory
        episodic = EpisodicStore(path=mem_cfg.episodic_path, max_entries=mem_cfg.episodic_max_entries)
        semantic = SemanticStore(
            path=mem_cfg.semantic_path,
            max_entries=mem_cfg.semantic_max_entries,
            vector_db_path=mem_cfg.vector_db_path,
        )
        memory_mgr = KernelFactory._build_memory(
            event_bus,
            config,
            episodic=episodic,
            semantic=semantic,
        )

        # ============================================================
        # Phase 3: 大脳辺縁系 (感情エンジン)
        # ============================================================
        big_five = BigFiveProfile.load()
        limbic = LimbicManager(
            event_bus=event_bus,
            emotional_memory=EmotionalMemory(
                episodic_store=episodic,
                semantic_store=semantic,
            ),
        )
        limbic.set_big_five(big_five)

        # ============================================================
        # Phase 4: LLM・パーソナリティ
        # ============================================================
        llm = KernelFactory._build_llm(config)
        tokenizers: dict[str, TokenizerManager] = {
            entry.name: TokenizerManager(
                repo_id=entry.tokenizer_repo_id,
                local_path=entry.tokenizer_local_path,
                hf_token=entry.tokenizer_hf_token,
            )
            for entry in config.model.models
        }

        # ============================================================
        # Phase 4: ケイパビリティ (ツール)
        # ============================================================
        _registry, tool_exec = KernelFactory._build_tools()

        # ============================================================
        # Phase 4.5: 基底核抑制
        # ============================================================
        inhibition = InhibitionController()

        # ============================================================
        # Phase 5: Agency 層 (PFC planning + 基底核 execution)
        # ============================================================
        internal_bus = InternalBus()
        scoring = ProactiveScoring(config=config.proactive, memory=memory_mgr)
        agency = KernelFactory._build_agency(
            config,
            event_bus,
            internal_bus,
            llm,
            memory_mgr,
            tool_exec,
            session_mgr,
            inhibition=inhibition,
            scoring=scoring,
            limbic=limbic,
            big_five=big_five,
            tokenizers=tokenizers,
        )

        # ============================================================
        # Phase 6: KernelManager + CommandHandler
        # ============================================================
        kernel_mgr = KernelManager()
        cmd_handler = CommandHandler(config=config)

        # ============================================================
        # Phase 7: コンテキスト組み立て
        # ============================================================
        ctx = KernelContext(
            event_bus=event_bus,
            kernel=kernel_mgr,
            io=io_mgr,
            limbic=limbic,
            memory=memory_mgr,
            agency=agency,
            cmd_handler=cmd_handler,
            tcp_listener=tcp_listener,
            session_mgr=session_mgr,
        )

        def _on_shutdown() -> None:
            ctx.shutdown_requested = True

        cmd_handler.set_shutdown_handler(_on_shutdown)
        cmd_handler.set_compact_handler(ctx.agency.compact_context)
        cmd_handler.set_memory(memory_mgr)
        cmd_handler.set_limbic(limbic)
        cmd_handler.set_session_mgr(session_mgr)
        cmd_handler.set_llm(llm)
        cmd_handler.set_registry(_registry)
        cmd_handler.set_big_five(big_five)
        ctx.io.set_command_handler(cmd_handler.handle)

        return ctx

    @staticmethod
    def _build_memory(
        event_bus: EventBus,
        config: Config,
        episodic: EpisodicStore | None = None,
        semantic: SemanticStore | None = None,
    ) -> MemoryManager:
        cfg = config.memory
        if episodic is None:
            episodic = EpisodicStore(path=cfg.episodic_path, max_entries=cfg.episodic_max_entries)
        if semantic is None:
            semantic = SemanticStore(
                path=cfg.semantic_path,
                max_entries=cfg.semantic_max_entries,
                vector_db_path=cfg.vector_db_path,
            )
        vector_store = VectorStore(path=cfg.vector_db_path)

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
        return mem

    @staticmethod
    def _build_llm(config: Config) -> LLMBridge:
        return LLMBridge(model_config=config.model)

    @staticmethod
    def _build_tools() -> tuple[ToolRegistry, ToolExecutionEngine]:
        registry = ToolRegistry()
        registry.discover_modules()
        tool_exec = ToolExecutionEngine(registry=registry)
        return registry, tool_exec

    @staticmethod
    def _build_agency(
        config: Config,
        event_bus: EventBus,
        internal_bus: InternalBus,
        llm: LLMBridge,
        memory: MemoryManager,
        tool_exec: ToolExecutionEngine,
        session_mgr: SessionManager,
        inhibition: InhibitionController,
        scoring: ProactiveScoring,
        limbic: LimbicManager | None = None,
        big_five: BigFiveProfile | None = None,
        tokenizers: dict[str, TokenizerManager] | None = None,
    ) -> AgencyManager:
        personality = Personality(name=config.personality.name, prompt_file=config.personality.prompt_file)
        capability_checker = CapabilityChecker(config=config.model)

        mem_cfg = config.memory
        agents_md_store = AgentsMdStore(path=mem_cfg.agents_md_path, max_bytes=mem_cfg.agents_md_max_bytes)
        persona_data = PersonaData()
        persona_profile = PersonaProfile(persona_data=persona_data)

        reflexion = Reflexion(llm=llm, compact_model=config.model.get_model("default"))
        hippocampal = HippocampalManager(
            reflexion=reflexion,
            memory=memory,
            persona_profile=persona_profile,
            big_five=big_five,
            reflect_interval=3,
        )

        pipeline = LLMPipeline(
            llm=llm,
            model_config=config.model,
            personality=personality,
            agents_md_store=agents_md_store,
            persona_profile=persona_profile,
            memory=memory,
            limbic=limbic,
            tool_executor=tool_exec,
            capability_checker=capability_checker,
        )

        planning = PlanningManager(
            internal_bus=internal_bus,
            event_bus=event_bus,
            inhibition=inhibition,
            scoring=scoring,
            config=config,
            memory=memory,
            limbic=limbic,
        )

        monitor = OutputMonitor(internal_bus=internal_bus)
        context_window_mgr = LLMContextWindowManager(
            llm=llm,
            compact_model=config.model.get_model("default"),
            tokenizers=tokenizers,
            default_model_name=config.model.get_model("default"),
        )
        execution = ExecutionManager(
            internal_bus=internal_bus,
            event_bus=event_bus,
            llm_pipeline=pipeline,
            context_window_mgr=context_window_mgr,
            context_window=config.model.default_context_window,
            model_config=config.model,
            hippocampal=hippocampal,
            monitor=monitor,
            inhibition=inhibition,
            session_roles_getter=session_mgr.get_sessions_summary,
            memory=memory,
        )

        return AgencyManager(
            planning=planning,
            execution=execution,
            inhibition=inhibition,
        )
