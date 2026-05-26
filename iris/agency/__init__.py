from __future__ import annotations

from typing import TYPE_CHECKING

from iris.agency.bus import InternalBus, PlanDecided
from iris.agency.execution import (
    NODE_TYPES,
    Consolidator,
    ExecutionOrchestrator,
    ExecutionState,
    FlowExecutor,
    LLMGateway,
    NodeType,
    ToolEngine,
)
from iris.agency.manager import AgencyManager
from iris.agency.planning import (
    Plan,
    PlanningManager,
    PlanReason,
    ProactiveJudge,
    ProactiveScoring,
    ScoreContext,
)
from iris.agency.task_level import TASK_LEVELS, TaskLevel
from iris.kernel.plugin import PluginCategory, PluginManifest, PluginPhase, PluginProtocol

if TYPE_CHECKING:
    from iris.kernel.manager import PluginManager

MANIFEST = PluginManifest(
    name="agency",
    version="0.1.0",
    category=PluginCategory.LAYER,
    phase=PluginPhase.COGNITIVE,
    dependencies={"EventBus", "LLMBridge", "MemoryManager", "ToolRegistry"},
    provides=["AgencyManager", "PlanningManager", "FlowExecutor"],
    description="高度認知層（PFC+基底核+運動野）",
)


class AgencyPlugin:
    MANIFEST = MANIFEST

    def init(self, manager: PluginManager) -> None:
        manager.register_manifest(MANIFEST)
        event_bus = manager.resolve("EventBus")
        config = manager.config
        llm = manager.resolve("LLMBridge")
        memory = manager.resolve("MemoryManager")
        tool_registry = manager.resolve("ToolRegistry")
        session_mgr = manager.resolve("SessionManager")
        debug_capture = manager.resolve_optional("DebugCapture")

        internal_bus = InternalBus()

        from iris.llm.prompt import Personality

        personality = Personality(name=config.personality.name, prompt_file=config.personality.prompt_file)
        capability_checker = manager.resolve_optional("CapabilityChecker")
        if capability_checker is None:
            from iris.llm.capability import CapabilityChecker

            capability_checker = CapabilityChecker(config=config.model)

        from iris.memory.long_term.stores import AgentsMdStore

        agents_md_store = AgentsMdStore(path=config.memory.agents_md_path, max_bytes=config.memory.agents_md_max_bytes)

        pipeline = LLMGateway(
            llm=llm,
            model_config=config.model,
            personality=personality,
            agents_md_store=agents_md_store,
            memory=memory,
            capability_checker=capability_checker,
            debug_capture=debug_capture,
            prompts_dir=config.personality.node_prompts_dir,
        )

        tool_exec = ToolEngine(registry=tool_registry)

        execution = FlowExecutor(
            internal_bus=internal_bus,
            event_bus=event_bus,
            llm_pipeline=pipeline,
            tool_executor=tool_exec,
            session_roles_getter=session_mgr.get_sessions_summary,
            memory=memory,
            capability_checker=CapabilityChecker(config=config.model),
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

        agency = AgencyManager(planning=planning, execution=execution)

        manager.provide("AgencyManager", agency)
        manager.provide("PlanningManager", planning)
        manager.provide("FlowExecutor", execution)
        manager.provide("LLMGateway", pipeline)
        manager.provide("ToolEngine", tool_exec)

        from .hooks import register_hooks

        register_hooks(manager)

    def start(self, manager: PluginManager) -> None:
        pass

    def stop(self, manager: PluginManager) -> None:
        agency = manager.resolve_optional("AgencyManager")
        if agency is not None and hasattr(agency, "shutdown"):
            agency.shutdown()


plugin: PluginProtocol = AgencyPlugin()

__all__ = [
    "NODE_TYPES",
    "TASK_LEVELS",
    "AgencyManager",
    "Consolidator",
    "ExecutionOrchestrator",
    "ExecutionState",
    "FlowExecutor",
    "InternalBus",
    "LLMGateway",
    "NodeType",
    "Plan",
    "PlanDecided",
    "PlanReason",
    "PlanningManager",
    "ProactiveJudge",
    "ProactiveScoring",
    "ScoreContext",
    "TaskLevel",
    "ToolEngine",
]
