from __future__ import annotations

from dataclasses import dataclass

from iris.capabilities.registry import CapabilityRegistry
from iris.commands.handler import CommandHandler
from iris.llm.capability_checker import CapabilityChecker
from iris.llm.llm_bridge import LLMBridge, create_provider
from iris.memory.persona_data import PersonaData
from iris.memory.persona_profile import PersonaProfile
from iris.memory.stores import AgentsMdStore, EpisodicStore, SemanticStore
from iris.memory.vector_store import VectorStore
from iris.personality.personality import Personality

from ..agent_state import AgentStateManager
from ..config import Config
from ..event.event_bus import EventBus
from ..io.control_manager import ControlManager
from ..io.input_manager import InputManager
from ..io.output_manager import OutputManager
from ..io.session_manager import SessionManager
from ..services.context import ContextManager
from ..services.conversation import ConversationService
from ..services.llm_pipeline import LLMPipeline
from ..services.memory_manager import MemoryManager
from ..services.proactive import SELF_GOVERNANCE_PRINCIPLES, ProactiveEngine
from ..services.reflexion import Reflexion
from ..services.reflexion_manager import ReflexionManager
from ..services.tool_executor import ToolExecutionEngine
from .agent_kernel import AgentKernel


@dataclass
class KernelContext:
    event_bus: EventBus
    kernel: AgentKernel
    conversation: ConversationService
    proactive: ProactiveEngine
    cmd_handler: CommandHandler
    output: OutputManager
    input_mgr: InputManager
    session_mgr: SessionManager
    control_mgr: ControlManager
    shutdown_requested: bool = False


class KernelFactory:
    @staticmethod
    def build(config: Config) -> KernelContext:
        event_bus = EventBus()
        state = AgentStateManager(event_bus=event_bus)
        session_mgr = SessionManager()
        output = OutputManager(session_manager=session_mgr)
        input_mgr = InputManager(session_manager=session_mgr)
        control_mgr = ControlManager(session_manager=session_mgr)

        memory, agents_md, persona_profile = KernelFactory._build_memory(config)
        llm, personality, capability_checker, reflexion, context_mgr = KernelFactory._build_llm(config)
        proactive, kernel = KernelFactory._build_proactive_and_kernel(
            config,
            event_bus,
            state,
            memory,
            llm,
            output,
        )
        registry, tool_exec = KernelFactory._build_capabilities()
        llm_pipeline, reflexion_mgr = KernelFactory._build_pipeline(
            config,
            llm,
            personality,
            agents_md,
            persona_profile,
            memory,
            tool_exec,
            capability_checker,
            context_mgr,
            reflexion,
        )

        conversation = ConversationService(
            output_manager=output,
            llm_pipeline=llm_pipeline,
            reflexion_manager=reflexion_mgr,
            context_manager=context_mgr,
            context_window=config.model.context_window,
        )
        cmd_handler = CommandHandler(
            state=state,
            conversation=conversation,
            proactive=proactive,
        )

        ctx = KernelContext(
            event_bus=event_bus,
            kernel=kernel,
            conversation=conversation,
            proactive=proactive,
            cmd_handler=cmd_handler,
            output=output,
            input_mgr=input_mgr,
            session_mgr=session_mgr,
            control_mgr=control_mgr,
        )

        from ..services.router import InputRouter

        input_mgr.set_on_input(InputRouter(ctx))

        return ctx

    @staticmethod
    def _build_memory(config: Config) -> tuple[MemoryManager, AgentsMdStore, PersonaProfile]:
        cfg = config.memory
        episodic = EpisodicStore(path=cfg.episodic_path, max_entries=cfg.episodic_max_entries)
        semantic = SemanticStore(
            path=cfg.semantic_path,
            max_entries=cfg.semantic_max_entries,
            vector_db_path=cfg.vector_db_path,
        )
        vector = VectorStore(path=cfg.vector_db_path)
        memory = MemoryManager(episodic=episodic, semantic=semantic, vector_store=vector)
        persona_data = PersonaData()
        persona_profile = PersonaProfile(persona_data=persona_data)
        agents_md = AgentsMdStore(path=cfg.agents_md_path, max_bytes=cfg.agents_md_max_bytes)
        return memory, agents_md, persona_profile

    @staticmethod
    def _build_llm(config: Config) -> tuple[LLMBridge, Personality, CapabilityChecker, Reflexion, ContextManager]:
        provider = create_provider(
            provider_type=config.model.provider,
            base_url=config.model.base_url,
            api_key=config.model.api_key,
            default_model=config.model.get_model("default"),
            num_gpu=config.model.num_gpu,
            num_ctx=config.model.num_ctx,
        )
        llm = LLMBridge(provider=provider)
        personality = Personality(name=config.personality.name)
        capability_checker = CapabilityChecker(config=config.model)
        reflexion = Reflexion(llm=llm, compact_model=config.model.get_model("compact"))
        context_mgr = ContextManager(llm=llm, compact_model=config.model.get_model("default"))
        return llm, personality, capability_checker, reflexion, context_mgr

    @staticmethod
    def _build_proactive_and_kernel(
        config: Config,
        event_bus: EventBus,
        state: AgentStateManager,
        memory: MemoryManager,
        llm: LLMBridge,
        output: OutputManager,
    ) -> tuple[ProactiveEngine, AgentKernel]:
        proactive = ProactiveEngine(
            config=config.proactive,
            event_bus=event_bus,
            output_manager=output,
            state_manager=state,
            memory=memory,
            llm=llm,
            fast_model=config.model.get_model("fast"),
        )
        kernel = AgentKernel(
            event_bus=event_bus,
            state_manager=state,
            proactive=proactive,
            memory=memory,
            config=config.proactive,
            output_manager=output,
        )
        proactive.set_approval_callback(kernel.evaluate_proactive_request)
        kernel.startup()
        return proactive, kernel

    @staticmethod
    def _build_capabilities() -> tuple[CapabilityRegistry, ToolExecutionEngine]:
        registry = CapabilityRegistry()
        registry.discover_modules()

        from iris.tools.builtins.output import output_to

        registry.register_decorated(output_to)

        tool_exec = ToolExecutionEngine(registry=registry)
        return registry, tool_exec

    @staticmethod
    def _build_pipeline(
        config: Config,
        llm: LLMBridge,
        personality: Personality,
        agents_md: AgentsMdStore,
        persona_profile: PersonaProfile,
        memory: MemoryManager,
        tool_exec: ToolExecutionEngine,
        capability_checker: CapabilityChecker,
        context_mgr: ContextManager,
        reflexion: Reflexion,
    ) -> tuple[LLMPipeline, ReflexionManager]:
        governance_str = "\n".join(f"- {p}" for p in SELF_GOVERNANCE_PRINCIPLES) if SELF_GOVERNANCE_PRINCIPLES else ""
        llm_pipeline = LLMPipeline(
            llm=llm,
            model_config=config.model,
            personality=personality,
            agents_md_store=agents_md,
            persona_profile=persona_profile,
            memory=memory,
            tool_executor=tool_exec,
            capability_checker=capability_checker,
            context_manager=context_mgr,
            governance_principles=governance_str,
        )
        reflexion_mgr = ReflexionManager(
            reflexion=reflexion,
            memory=memory,
            persona_profile=persona_profile,
            reflect_interval=3,
        )
        return llm_pipeline, reflexion_mgr
