from __future__ import annotations

from dataclasses import dataclass

from loguru import logger

from iris.agency.bus import InternalBus
from iris.agency.execution.engine import ToolEngine
from iris.agency.execution.executor import FlowExecutor
from iris.agency.execution.llm.gateway import LLMGateway
from iris.agency.execution.regulation.consolidator import Consolidator
from iris.agency.execution.regulation.output_tracker import OutputTracker
from iris.agency.inhibition import InhibitionController
from iris.agency.manager import AgencyManager
from iris.agency.planning.decisions import ProactiveScoring
from iris.agency.planning.manager import PlanningManager
from iris.event.event_bus import EventBus
from iris.event.tracer import EventTracer
from iris.io.manager import IOManager
from iris.io.session.manager import SessionConfig, SessionManager
from iris.io.transport.grpc_server import GrpcListener
from iris.kernel.commands.handler import CommandHandler
from iris.kernel.debug_capture import DebugCapture
from iris.kernel.diagnostics import SystemDiagnostics
from iris.limbic.hippocampus.binder import EmotionalMemory
from iris.limbic.manager import LimbicManager
from iris.limbic.prefrontal.personality import BigFiveProfile
from iris.limbic.score import PsychometricState
from iris.llm.bridge import LLMBridge
from iris.llm.capability import CapabilityChecker
from iris.llm.context import LLMContextWindowManager
from iris.llm.prompt import Personality
from iris.llm.tokenizer import TokenizerManager
from iris.memory.hippocampal.manager import HippocampalManager
from iris.memory.hippocampal.reflexion import Reflexion
from iris.memory.long_term.manager import LongTermMemoryManager
from iris.memory.long_term.stores import AgentsMdStore, EpisodicStore, SemanticStore
from iris.memory.long_term.vector_store import VectorStore
from iris.memory.manager import MemoryManager
from iris.memory.persona_data import PersonaData
from iris.memory.persona_profile import PersonaProfile
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
        logger.warning("Could not set strict permissions (0600) on %s", secrets_path)
    logger.info("Generated access_token and saved to .iris/secrets.yaml")


@dataclass
class KernelContext:
    event_bus: EventBus
    kernel: KernelManager
    io: IOManager
    limbic: LimbicManager | None
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

        if debug:
            return KernelFactory._build_shared(
                config,
                event_bus,
                tracer,
                io_mgr,
                session_mgr,
                grpc_listener,
                memory_mgr=None,
                limbic=None,
                llm=None,
                debug_capture=None,
                registry=None,
                agency=None,
                big_five=None,
            )

        (episodic, semantic) = KernelFactory._build_stores(config)
        memory_mgr = KernelFactory._build_memory(event_bus, config, episodic=episodic, semantic=semantic)

        psychometric = PsychometricState(path=config.memory.psychometric_state_path)

        big_five = BigFiveProfile()
        big_five.set_state(psychometric)
        limbic = LimbicManager(
            event_bus=event_bus,
            emotional_memory=EmotionalMemory(episodic_store=episodic, semantic_store=semantic),
        )
        limbic.set_big_five(big_five)
        limbic.set_psychometric_state(psychometric)

        llm = KernelFactory._build_llm(config)
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
        _registry, tool_exec = KernelFactory._build_tools()
        agency = KernelFactory._build_agency(
            config,
            event_bus,
            llm,
            memory_mgr,
            tool_exec,
            session_mgr,
            limbic=limbic,
            big_five=big_five,
            psychometric=psychometric,
            tokenizers=tokenizers,
            debug_capture=debug_capture,
        )

        return KernelFactory._build_shared(
            config,
            event_bus,
            tracer,
            io_mgr,
            session_mgr,
            grpc_listener,
            memory_mgr=memory_mgr,
            limbic=limbic,
            llm=llm,
            debug_capture=debug_capture,
            registry=_registry,
            agency=agency,
            big_five=big_five,
        )

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
        memory_mgr: MemoryManager | None,
        limbic: LimbicManager | None,
        llm: LLMBridge | None,
        debug_capture: DebugCapture | None,
        registry: ToolRegistry | None,
        agency: AgencyManager | None,
        big_five: BigFiveProfile | None,
    ) -> KernelContext:
        kernel_mgr = KernelManager()
        diagnostics = SystemDiagnostics(
            event_bus=event_bus,
            tracer=tracer,
            kernel=kernel_mgr,
            io=io_mgr,
            memory=memory_mgr,
            limbic=limbic,
            agency=agency,
        )

        ctx = KernelContext(
            event_bus=event_bus,
            kernel=kernel_mgr,
            io=io_mgr,
            limbic=limbic,
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
            on_compact=ctx.agency.execution.compact_context if ctx.agency else _noop_compact,
            memory=memory_mgr,
            limbic=limbic,
            session_mgr=session_mgr,
            llm=llm,
            registry=registry,
            big_five=big_five,
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
        limbic: LimbicManager | None = None,
        big_five: BigFiveProfile | None = None,
        psychometric: PsychometricState | None = None,
        tokenizers: dict[str, TokenizerManager] | None = None,
        debug_capture: DebugCapture | None = None,
    ) -> AgencyManager:
        inhibition = InhibitionController()
        internal_bus = InternalBus()

        personality = Personality(name=config.personality.name, prompt_file=config.personality.prompt_file)
        capability_checker = CapabilityChecker(config=config.model)

        mem_cfg = config.memory
        agents_md_store = AgentsMdStore(path=mem_cfg.agents_md_path, max_bytes=mem_cfg.agents_md_max_bytes)
        persona_data = PersonaData()
        if psychometric is not None:
            persona_data.set_state(psychometric)
        persona_profile = PersonaProfile(persona_data=persona_data)
        if limbic is not None:
            limbic.set_persona_profile(persona_profile)

        reflexion = Reflexion(llm=llm, compact_model=config.model.get_model("default"))
        hippocampal = HippocampalManager(
            reflexion=reflexion,
            memory=memory,
            persona_profile=persona_profile,
            big_five=big_five,
            reflect_interval=3,
            event_bus=event_bus,
        )

        pipeline = LLMGateway(
            llm=llm,
            model_config=config.model,
            personality=personality,
            agents_md_store=agents_md_store,
            persona_profile=persona_profile,
            memory=memory,
            limbic=limbic,
            capability_checker=capability_checker,
            debug_capture=debug_capture,
        )

        scoring = ProactiveScoring(config=config.proactive, memory=memory)
        planning = PlanningManager(
            internal_bus=internal_bus,
            event_bus=event_bus,
            inhibition=inhibition,
            scoring=scoring,
            config=config,
            memory=memory,
            limbic=limbic,
            persona_profile=persona_profile,
            llm=llm,
        )

        monitor = OutputTracker(internal_bus=internal_bus)
        context_window_mgr = LLMContextWindowManager(
            llm=llm,
            compact_model=config.model.get_model("default"),
            tokenizers=tokenizers,
            default_model_name=config.model.get_model("default"),
        )
        consolidator = Consolidator(
            event_bus=event_bus,
            messages_getter=lambda: execution._messages,
            hippocampal=hippocampal,
            context_window_mgr=context_window_mgr,
            model_config=config.model,
            context_window=config.model.default_context_window,
            inhibition=inhibition,
            config=config,
        )
        execution = FlowExecutor(
            internal_bus=internal_bus,
            event_bus=event_bus,
            llm_pipeline=pipeline,
            consolidator=consolidator,
            tool_executor=tool_exec,
            monitor=monitor,
            inhibition=inhibition,
            session_roles_getter=session_mgr.get_sessions_summary,
            memory=memory,
            capability_checker=capability_checker,
        )

        return AgencyManager(
            planning=planning,
            execution=execution,
            inhibition=inhibition,
        )
