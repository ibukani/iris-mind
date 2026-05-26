from __future__ import annotations

from dataclasses import dataclass

from loguru import logger

from iris.agency import (
    AgencyManager,
    FlowExecutor,
    InternalBus,
    LLMGateway,
    PlanningManager,
    ProactiveScoring,
    ToolEngine,
)
from iris.event.event_bus import EventBus
from iris.event.tracer import EventTracer
from iris.io.manager import IOManager
from iris.io.session.manager import SessionConfig, SessionManager
from iris.io.transport.grpc_server import GrpcListener
from iris.kernel.commands.handler import CommandHandler
from iris.kernel.debug_capture import DebugCapture
from iris.kernel.diagnostics import SystemDiagnostics
from iris.llm.bridge import LLMBridge
from iris.llm.capability import CapabilityChecker
from iris.llm.prompt import Personality
from iris.llm.tokenizer import TokenizerManager
from iris.memory.long_term.manager import LongTermMemoryManager
from iris.memory.long_term.stores import AgentsMdStore, EpisodicStore, SemanticStore
from iris.memory.long_term.vector_store import VectorStore
from iris.memory.manager import MemoryManager
from iris.memory.sensory.manager import SensoryMemoryManager
from iris.memory.sensory.readiness import ReadinessEvaluator
from iris.memory.short_term.manager import ShortTermMemoryManager
from iris.tools.registry import ToolRegistry

from .config import Config
from .manager import KernelManager


def _ensure_access_token(config: Config) -> None:
    import os as _os
    from pathlib import Path as _Path

    token = _os.environ.get("IRIS_ACCESS_TOKEN", "")
    if token:
        config.session.access_token = token
        return

    if config.session.access_token:
        return

    secrets_path = _Path(".iris/secrets.yaml")
    if secrets_path.exists():
        import yaml as _yaml

        secrets = _yaml.safe_load(secrets_path.read_text(encoding="utf-8"))
        if secrets and "access_token" in secrets:
            config.session.access_token = secrets["access_token"]
            return

    from iris.io.auth.authenticator import Authenticator as _Auth

    token = _Auth.generate_token()
    config.session.access_token = token
    secrets_path.parent.mkdir(parents=True, exist_ok=True)
    import yaml as _yaml

    secrets_path.write_text(
        _yaml.dump({"access_token": token}, default_flow_style=False),
        encoding="utf-8",
    )
    try:
        secrets_path.chmod(0o600)
    except Exception:
        logger.warning("Could not set strict permissions (0600) on {}", secrets_path)
    logger.info("Generated access_token and saved to .iris/secrets.yaml")


@dataclass
class KernelContext:
    event_bus: EventBus
    kernel: KernelManager
    io: IOManager
    memory: MemoryManager | None
    agency: AgencyManager | None
    cmd_handler: CommandHandler
    grpc_listener: GrpcListener
    session_mgr: SessionManager
    diagnostics: SystemDiagnostics | None = None
    shutdown_requested: bool = False


class KernelFactory:
    @staticmethod
    def build(config: Config, debug: bool = False) -> KernelContext:
        _ensure_access_token(config)
        tracer, event_bus, io_mgr, session_mgr, grpc_listener = KernelFactory._build_infrastructure(config)

        if debug:
            return KernelFactory._build_shared(
                config,
                event_bus,
                tracer,
                io_mgr,
                session_mgr,
                grpc_listener,
            )

        memory_mgr = KernelFactory._build_cognitive_layers(config, event_bus)
        llm, tokenizers, debug_capture = KernelFactory._build_llm_layer(config)
        registry, agency = KernelFactory._build_agency_layer(
            config, event_bus, llm, memory_mgr, session_mgr, tokenizers, debug_capture
        )

        return KernelFactory._build_shared(
            config,
            event_bus,
            tracer,
            io_mgr,
            session_mgr,
            grpc_listener,
            memory_mgr=memory_mgr,
            llm=llm,
            debug_capture=debug_capture,
            registry=registry,
            agency=agency,
        )

    @staticmethod
    def _build_infrastructure(config: Config) -> tuple[EventTracer, EventBus, IOManager, SessionManager, GrpcListener]:
        tracer = EventTracer(max_entries=config.debug.trace_max_entries)
        tracer.set_enabled(config.debug.enabled)
        event_bus = EventBus(tracer=tracer)
        session_mgr = SessionManager(
            config=SessionConfig(**config.session.model_dump()),
            event_bus=event_bus,
        )
        grpc_listener = GrpcListener(session_manager=session_mgr)
        io_mgr = IOManager(
            event_bus=event_bus,
            session_manager=session_mgr,
            grpc_listener=grpc_listener,
        )
        return tracer, event_bus, io_mgr, session_mgr, grpc_listener

    @staticmethod
    def _build_cognitive_layers(config: Config, event_bus: EventBus) -> MemoryManager:
        episodic, semantic = KernelFactory._build_stores(config)
        return KernelFactory._build_memory(event_bus, config, episodic=episodic, semantic=semantic)

    @staticmethod
    def _build_llm_layer(
        config: Config,
    ) -> tuple[LLMBridge, dict[str, TokenizerManager], DebugCapture]:
        llm = LLMBridge(model_config=config.model)
        tokenizers: dict[str, TokenizerManager] = {
            entry.name: TokenizerManager(
                repo_id=entry.tokenizer_repo_id,
                local_path=entry.tokenizer_local_path,
                hf_token=config.model.hf_token,
            )
            for entry in config.model.models
        }
        debug_capture = DebugCapture(
            tokenizer_mgr=next(iter(tokenizers.values()), None),
            auto_dump=config.debug.capture_auto_dump,
            max_entries=config.debug.capture_max_entries,
        )
        if config.debug.capture_enabled:
            debug_capture.set_enabled(True)
        return llm, tokenizers, debug_capture

    @staticmethod
    def _build_agency_layer(
        config: Config,
        event_bus: EventBus,
        llm: LLMBridge,
        memory_mgr: MemoryManager,
        session_mgr: SessionManager,
        tokenizers: dict[str, TokenizerManager],
        debug_capture: DebugCapture,
    ) -> tuple[ToolRegistry, AgencyManager]:
        registry, tool_exec = KernelFactory._build_tools()
        agency = KernelFactory._build_agency(
            config,
            event_bus,
            llm,
            memory_mgr,
            tool_exec,
            session_mgr,
            tokenizers=tokenizers,
            debug_capture=debug_capture,
        )
        return registry, agency

    @staticmethod
    def _build_stores(config: Config) -> tuple[EpisodicStore, SemanticStore]:
        mem_cfg = config.memory
        return (
            EpisodicStore(path=mem_cfg.episodic_path, max_entries=mem_cfg.episodic_max_entries),
            SemanticStore(
                path=mem_cfg.semantic_path,
                max_entries=mem_cfg.semantic_max_entries,
                vector_db_path=mem_cfg.vector_db_path,
            ),
        )

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
    def _build_tools() -> tuple[ToolRegistry, ToolEngine]:
        registry = ToolRegistry()
        registry.discover_modules()
        tool_exec = ToolEngine(registry=registry)
        return registry, tool_exec

    @staticmethod
    def _build_shared(
        config: Config,
        event_bus: EventBus,
        tracer: EventTracer,
        io_mgr: IOManager,
        session_mgr: SessionManager,
        grpc_listener: GrpcListener,
        memory_mgr: MemoryManager | None = None,
        llm: LLMBridge | None = None,
        debug_capture: DebugCapture | None = None,
        registry: ToolRegistry | None = None,
        agency: AgencyManager | None = None,
    ) -> KernelContext:
        kernel_mgr = KernelManager()
        diagnostics = SystemDiagnostics(
            event_bus=event_bus,
            tracer=tracer,
            kernel=kernel_mgr,
            io=io_mgr,
            memory=memory_mgr,
            agency=agency,
        )

        ctx = KernelContext(
            event_bus=event_bus,
            kernel=kernel_mgr,
            io=io_mgr,
            memory=memory_mgr,
            agency=agency,
            cmd_handler=None,  # type: ignore[arg-type]
            grpc_listener=grpc_listener,
            session_mgr=session_mgr,
            diagnostics=diagnostics,
        )

        def _on_shutdown() -> None:
            ctx.shutdown_requested = True

        def _noop_compact() -> str:
            return "Compact not available (debug mode)"

        cmd_handler = CommandHandler(
            config=config,
            on_shutdown=_on_shutdown,
            on_compact=ctx.agency.compact_context if ctx.agency else _noop_compact,
            memory=memory_mgr,
            session_mgr=session_mgr,
            llm=llm,
            registry=registry,
            debug_capture=debug_capture,
            diagnostics=diagnostics,
        )
        ctx.cmd_handler = cmd_handler
        ctx.io.set_command_handler(cmd_handler.handle)

        return ctx

    @staticmethod
    def _build_agency(
        config: Config,
        event_bus: EventBus,
        llm: LLMBridge,
        memory: MemoryManager,
        tool_exec: ToolEngine,
        session_mgr: SessionManager,
        tokenizers: dict[str, TokenizerManager] | None = None,
        debug_capture: DebugCapture | None = None,
    ) -> AgencyManager:
        internal_bus = InternalBus()

        pipeline = KernelFactory._build_llm_pipeline(config, event_bus, llm, memory, debug_capture)
        execution = KernelFactory._build_execution(
            config, event_bus, llm, memory, tool_exec, session_mgr, internal_bus, pipeline, tokenizers
        )

        scoring = ProactiveScoring(config=config.proactive, memory=memory)
        planning = PlanningManager(
            internal_bus=internal_bus,
            event_bus=event_bus,
            scoring=scoring,
            config=config,
            memory=memory,
            llm=llm,
        )

        return AgencyManager(planning=planning, execution=execution)

    @staticmethod
    def _build_llm_pipeline(
        config: Config,
        event_bus: EventBus,
        llm: LLMBridge,
        memory: MemoryManager,
        debug_capture: DebugCapture | None,
    ) -> LLMGateway:
        personality = Personality(name=config.personality.name, prompt_file=config.personality.prompt_file)
        capability_checker = CapabilityChecker(config=config.model)

        mem_cfg = config.memory
        agents_md_store = AgentsMdStore(path=mem_cfg.agents_md_path, max_bytes=mem_cfg.agents_md_max_bytes)

        return LLMGateway(
            llm=llm,
            model_config=config.model,
            personality=personality,
            agents_md_store=agents_md_store,
            memory=memory,
            capability_checker=capability_checker,
            debug_capture=debug_capture,
            prompts_dir=config.personality.node_prompts_dir,
        )

    @staticmethod
    def _build_execution(
        config: Config,
        event_bus: EventBus,
        llm: LLMBridge,
        memory: MemoryManager,
        tool_exec: ToolEngine,
        session_mgr: SessionManager,
        internal_bus: InternalBus,
        pipeline: LLMGateway,
        tokenizers: dict[str, TokenizerManager] | None,
    ) -> FlowExecutor:
        return FlowExecutor(
            internal_bus=internal_bus,
            event_bus=event_bus,
            llm_pipeline=pipeline,
            tool_executor=tool_exec,
            session_roles_getter=session_mgr.get_sessions_summary,
            memory=memory,
            capability_checker=CapabilityChecker(config=config.model),
        )
