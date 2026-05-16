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
from iris.event.event_bus import EventBus
from iris.io.session.manager import SessionConfig, SessionManager
from iris.io.transport.tcp_listener import TcpListener
from ..services.context import ContextManager
from ..services.conversation import ConversationService
from ..services.llm_pipeline import LLMPipeline
from ..services.memory_manager import MemoryManager
from ..services.proactive import SELF_GOVERNANCE_PRINCIPLES, ProactiveEngine
from ..services.reflexion import Reflexion
from ..services.reflexion_manager import ReflexionManager
from ..services.response_readiness import ResponseReadinessEvaluator
from ..services.tool_executor import ToolExecutionEngine
from .agent_kernel import AgentKernel


@dataclass
class KernelContext:
    event_bus: EventBus
    kernel: AgentKernel
    conversation: ConversationService
    proactive: ProactiveEngine
    cmd_handler: CommandHandler
    tcp_listener: TcpListener
    session_mgr: SessionManager
    shutdown_requested: bool = False


class KernelFactory:
    @staticmethod
    def build(config: Config) -> KernelContext:
        # ============================================================
        # Phase 1: インフラ基盤 (I/O・イベント・セッション)
        # ============================================================
        event_bus = EventBus()
        state = AgentStateManager(event_bus=event_bus)
        session_mgr = SessionManager(config=SessionConfig(**config.session.model_dump()))
        tcp_listener = TcpListener(session_manager=session_mgr)

        # ============================================================
        # Phase 2: 記憶レイヤー
        # ============================================================
        memory, agents_md, persona_profile = KernelFactory._build_memory(config)

        # ============================================================
        # Phase 3: LLM・パーソナリティレイヤー
        # ============================================================
        llm, personality, capability_checker, reflexion, context_mgr = KernelFactory._build_llm(config)

        # ============================================================
        # Phase 4: ケイパビリティ (ツール) レイヤー
        # ============================================================
        registry, tool_exec = KernelFactory._build_capabilities()

        # ============================================================
        # Phase 5: パイプライン (LLM処理・内省)
        # 依存: Phase 3 (llm, personality, ...) + Phase 4 (tool_exec)
        # ============================================================
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

        # ============================================================
        # Phase 5.5: 準同期応答準備評価
        # 依存: Phase 3 (llm)
        # ============================================================
        qs_cfg = config.quasi_sync
        readiness: ResponseReadinessEvaluator | None = None
        if qs_cfg.enabled:
            readiness = ResponseReadinessEvaluator(
                config=qs_cfg.response_readiness,
                llm=llm,
            )

        # ============================================================
        # Phase 6: 会話サービス
        # 依存: Phase 1 (output) + Phase 5 (llm_pipeline, reflexion_mgr, context_mgr) + Phase 5.5 (readiness)
        # ============================================================
        conversation = ConversationService(
            session_manager=session_mgr,
            llm_pipeline=llm_pipeline,
            state_manager=state,
            reflexion_manager=reflexion_mgr,
            context_manager=context_mgr,
            context_window=config.model.context_window,
            quasi_timeout_ms=qs_cfg.input_timeout_ms,
            quasi_max_fragments=qs_cfg.max_buffer_fragments,
            readiness_config=qs_cfg.response_readiness,
            readiness_evaluator=readiness,
        )

        # ============================================================
        # Phase 7: 自発発話エンジン + カーネル (起動はPhase 9で)
        # 依存: Phase 1 (event_bus, state, output) + Phase 2 (memory) + Phase 3 (llm)
        # ============================================================
        proactive, kernel = KernelFactory._build_proactive_and_kernel(
            config,
            event_bus,
            state,
            memory,
            llm,
            session_mgr,
        )

        # ============================================================
        # Phase 8: コマンドハンドラ
        # 依存: Phase 1 (state) + Phase 6 (conversation) + Phase 7 (proactive)
        # ============================================================
        cmd_handler = CommandHandler(
            state=state,
            conversation=conversation,
            proactive=proactive,
        )

        # ============================================================
        # Phase 9: コンテキスト組み立て + ルーター設定 + カーネル起動
        # ============================================================
        ctx = KernelContext(
            event_bus=event_bus,
            kernel=kernel,
            conversation=conversation,
            proactive=proactive,
            cmd_handler=cmd_handler,
            tcp_listener=tcp_listener,
            session_mgr=session_mgr,
        )

        from ..services.router import InputRouter

        tcp_listener.set_on_input(InputRouter(ctx))
        tcp_listener.set_on_interrupt(ctx.conversation.interrupt)

        # カーネル起動は全接続完了後に実行
        kernel.startup()

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
        session_mgr: SessionManager,
    ) -> tuple[ProactiveEngine, AgentKernel]:
        proactive = ProactiveEngine(
            config=config.proactive,
            event_bus=event_bus,
            session_manager=session_mgr,
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
            session_manager=session_mgr,
        )
        proactive.set_approval_callback(kernel.evaluate_proactive_request)
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
