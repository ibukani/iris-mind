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
from iris.limbic.manager import LimbicManager
from iris.llm.capability_checker import CapabilityChecker
from iris.llm.context_window import LLMContextWindowManager
from iris.llm.llm_bridge import LLMBridge, create_provider
from iris.memory.hippocampal.manager import HippocampalManager
from iris.memory.hippocampal.reflexion import Reflexion
from iris.memory.manager import MemoryManager
from iris.memory.personality.persona_data import PersonaData
from iris.memory.personality.persona_profile import PersonaProfile
from iris.memory.personality.personality import Personality
from iris.memory.sensory.buffer import InputBuffer
from iris.memory.sensory.readiness import ReadinessEvaluator
from iris.memory.stores import AgentsMdStore, EpisodicStore, SemanticStore
from iris.memory.vector_store import VectorStore
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
        # Phase 2: 記憶レイヤー
        # ============================================================
        memory_mgr = KernelFactory._build_memory(event_bus, config)

        # ============================================================
        # Phase 3: 大脳辺縁系 (感情エンジン)
        # ============================================================
        limbic = LimbicManager(event_bus=event_bus)

        # ============================================================
        # Phase 4: LLM・パーソナリティ
        # ============================================================
        llm = KernelFactory._build_llm(config)

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
        ctx.io.set_command_handler(cmd_handler.handle)

        return ctx

    @staticmethod
    def _build_memory(event_bus: EventBus, config: Config) -> MemoryManager:
        cfg = config.memory
        episodic = EpisodicStore(path=cfg.episodic_path, max_entries=cfg.episodic_max_entries)
        semantic = SemanticStore(
            path=cfg.semantic_path,
            max_entries=cfg.semantic_max_entries,
            vector_db_path=cfg.vector_db_path,
        )
        vector_store = VectorStore(path=cfg.vector_db_path)
        mem = MemoryManager(
            event_bus=event_bus,
            episodic=episodic,
            semantic=semantic,
            vector_store=vector_store,
            proactive_config=config.proactive,
        )
        buf = InputBuffer(session_id="0" * 16)
        readiness = ReadinessEvaluator(
            min_fragments=config.quasi_sync.response_readiness.tier1_min_fragments,
            question_detect=config.quasi_sync.response_readiness.tier1_question_detect,
            confidence_threshold=config.quasi_sync.response_readiness.confidence_threshold,
            llm=None,
            llm_model_role=config.quasi_sync.response_readiness.llm_model_role,
        )
        buf.set_readiness_evaluator(readiness)
        mem.set_sensory_buffer(buf)
        return mem

    @staticmethod
    def _build_llm(config: Config) -> LLMBridge:
        provider = create_provider(
            provider_type=config.model.provider,
            base_url=config.model.base_url,
            api_key=config.model.api_key,
            default_model=config.model.get_model("default"),
            num_gpu=config.model.num_gpu,
            num_ctx=config.model.num_ctx,
        )
        return LLMBridge(provider=provider)

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
        context_window_mgr = LLMContextWindowManager(llm=llm, compact_model=config.model.get_model("default"))
        execution = ExecutionManager(
            internal_bus=internal_bus,
            event_bus=event_bus,
            llm_pipeline=pipeline,
            context_window_mgr=context_window_mgr,
            context_window=config.model.context_window,
            hippocampal=hippocampal,
            monitor=monitor,
            inhibition=inhibition,
            session_roles_getter=session_mgr.get_roles_summary,
        )

        return AgencyManager(
            planning=planning,
            execution=execution,
            inhibition=inhibition,
        )
