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

        from iris.agency.builder import build_agency

        components = build_agency(manager)

        manager.provide(AgencyManager, components["agency"])
        manager.provide(PlanningManager, components["planning"])
        manager.provide(FlowExecutor, components["execution"])
        manager.provide(LLMGateway, components["pipeline"])
        manager.provide(ToolEngine, components["tool_exec"])

        from .hooks import register_hooks

        register_hooks(manager)

    def start(self, manager: PluginManager) -> None:
        pass

    def stop(self, manager: PluginManager) -> None:
        from iris.agency.manager import AgencyManager

        agency = manager.resolve_optional(AgencyManager)
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
