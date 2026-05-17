from __future__ import annotations

import logging
from dataclasses import dataclass

from iris.capabilities.registry import CapabilityRegistry
from iris.commands.handler import CommandHandler
from iris.llm.capability_checker import CapabilityChecker
from iris.llm.llm_bridge import LLMBridge, create_provider
from iris.memory.stores import EpisodicStore, SemanticStore
from iris.memory.vector_store import VectorStore
from iris.personality.personality import Personality

from ..config import Config
from iris.event.event_bus import EventBus
from iris.memory.sensory.buffer import InputBuffer
from iris.io.session.manager import SessionConfig, SessionManager
from iris.io.transport.tcp_listener import TcpListener
from iris.io.manager import IOManager
from iris.memory.manager import MemoryManager
from iris.agency.bus import InternalBus
from iris.agency.manager import AgencyManager
from iris.agency.planning.manager import PlanningManager
from iris.agency.execution.manager import ExecutionManager
from iris.agency.execution.pipeline import LLMPipeline
from iris.agency.execution.tool_executor import ToolExecutionEngine
from ..manager import KernelManager

logger = logging.getLogger(__name__)


@dataclass
class KernelContext:
    event_bus: EventBus
    kernel: KernelManager
    io: IOManager
    memory: MemoryManager
    agency: AgencyManager
    cmd_handler: CommandHandler
    tcp_listener: TcpListener
    session_mgr: SessionManager
    shutdown_requested: bool = False


class KernelFactory:
    @staticmethod
    def build(config: Config) -> KernelContext:
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
        # Phase 3: LLM・パーソナリティ
        # ============================================================
        llm = KernelFactory._build_llm(config)

        # ============================================================
        # Phase 4: ケイパビリティ (ツール)
        # ============================================================
        registry, tool_exec = KernelFactory._build_capabilities()

        # ============================================================
        # Phase 5: Agency 層 (planning + execution)
        # ============================================================
        internal_bus = InternalBus()
        agency = KernelFactory._build_agency(
            config, event_bus, internal_bus, llm, memory_mgr, tool_exec, session_mgr,
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
            memory=memory_mgr,
            agency=agency,
            cmd_handler=cmd_handler,
            tcp_listener=tcp_listener,
            session_mgr=session_mgr,
        )

        def _on_shutdown() -> None:
            ctx.shutdown_requested = True

        cmd_handler.set_shutdown_handler(_on_shutdown)

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
        vector = VectorStore(path=cfg.vector_db_path)
        mem = MemoryManager(
            event_bus=event_bus,
            episodic=episodic,
            semantic=semantic,
            vector_store=vector,
        )
        buf = InputBuffer(session_id="0" * 16)
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
    def _build_capabilities() -> tuple[CapabilityRegistry, ToolExecutionEngine]:
        registry = CapabilityRegistry()
        registry.discover_modules()

        from iris.tools.builtins.output import output_to

        registry.register_decorated(output_to)

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
    ) -> AgencyManager:
        personality = Personality(name=config.personality.name)
        capability_checker = CapabilityChecker(config=config.model)

        pipeline = LLMPipeline(
            llm=llm,
            model_config=config.model,
            personality=personality,
            agents_md_store=None,
            persona_profile=None,
            memory=memory,
            tool_executor=tool_exec,
            capability_checker=capability_checker,
        )
        planning = PlanningManager(internal_bus=internal_bus)
        execution = ExecutionManager(
            internal_bus=internal_bus,
            event_bus=event_bus,
            llm_pipeline=pipeline,
            session_roles_getter=session_mgr.get_roles_summary,
        )
        return AgencyManager(
            event_bus=event_bus,
            internal_bus=internal_bus,
            planning=planning,
            execution=execution,
        )
