"""
KernelFactory — Iris カーネルコンポーネントの組み立て。

Adapter は KernelFactory.build(config) で組み立て済みの KernelContext を
受け取り、内部の依存関係構築を意識せずに動作できる。
"""

from __future__ import annotations

from dataclasses import dataclass

from iris.capabilities.registry import CapabilityRegistry
from iris.commands.handler import CommandHandler
from iris.llm.llm_bridge import LLMBridge, create_provider
from iris.memory.persona_data import PersonaData
from iris.memory.persona_profile import PersonaProfile
from iris.memory.stores import AgentsMdStore, EpisodicStore, SemanticStore
from iris.memory.vector_store import VectorStore
from iris.personality.personality import Personality

from .agent_kernel import AgentKernel
from .agent_state import AgentStateManager
from .config import Config
from .context import ContextManager
from .conversation import ConversationService
from .event_bus import EventBus
from .memory_manager import MemoryManager
from .proactive import ProactiveEngine
from .reflexion import Reflexion
from .tool_executor import ToolExecutionEngine


@dataclass
class KernelContext:
    """組み立て済みカーネルコンポーネントのコンテナ。

    Adapter はこのオブジェクトを受け取り、必要なコンポーネントにアクセスする。
    """

    event_bus: EventBus
    kernel: AgentKernel
    conversation: ConversationService
    proactive: ProactiveEngine
    cmd_handler: CommandHandler


class KernelFactory:
    """カーネルコンポーネントの組み立てを担当するファクトリ。"""

    @staticmethod
    def build(config: Config) -> KernelContext:
        """設定に基づき全コンポーネントを組み立てる。"""
        event_bus = EventBus()
        state = AgentStateManager(event_bus=event_bus)

        # 記憶ストア
        cfg = config.memory
        episodic = EpisodicStore(
            path=cfg.episodic_path,
            max_entries=cfg.episodic_max_entries,
        )
        semantic = SemanticStore(
            path=cfg.semantic_path,
            max_entries=cfg.semantic_max_entries,
            vector_db_path=cfg.vector_db_path,
        )
        vector = VectorStore(path=cfg.vector_db_path)
        memory = MemoryManager(
            episodic=episodic,
            semantic=semantic,
            vector_store=vector,
        )

        # ペルソナデータ + 構造記憶
        persona_data = PersonaData()
        persona_profile = PersonaProfile(persona_data=persona_data)
        agents_md = AgentsMdStore(
            path=cfg.agents_md_path,
            max_bytes=cfg.agents_md_max_bytes,
        )

        # LLM + 会話関連サービス
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
        reflexion = Reflexion(llm=llm)
        context_mgr = ContextManager(
            llm=llm,
            compact_model=config.model.get_model("default"),
        )

        # 自発発話エンジン
        proactive = ProactiveEngine(
            config=config.proactive,
            event_bus=event_bus,
            state_manager=state,
            memory=memory,
            llm=llm,
        )

        # カーネル
        kernel = AgentKernel(
            event_bus=event_bus,
            state_manager=state,
            proactive=proactive,
            memory=memory,
            config=config.proactive,
        )
        proactive.set_approval_callback(kernel.evaluate_proactive_request)
        kernel.startup()

        # Capability registry + tool executor
        registry = CapabilityRegistry()
        registry.discover_modules()
        tool_exec = ToolExecutionEngine(registry=registry)

        # 会話サービス（カーネル起動後に生成 → イベント購読順を保証）
        conversation = ConversationService(
            event_bus=event_bus,
            memory=memory,
            llm=llm,
            personality=personality,
            config=config,
            reflexion=reflexion,
            tool_executor=tool_exec,
            context_manager=context_mgr,
            persona_profile=persona_profile,
            agents_md_store=agents_md,
        )

        # コマンドハンドラ
        cmd_handler = CommandHandler(
            state=state,
            conversation=conversation,
            proactive=proactive,
        )

        return KernelContext(
            event_bus=event_bus,
            kernel=kernel,
            conversation=conversation,
            proactive=proactive,
            cmd_handler=cmd_handler,
        )
