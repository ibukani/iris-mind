"""Agencyレイヤーのコンポーネント組み立て。"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from iris.kernel.manager import PluginManager


def build_agency(manager: PluginManager) -> dict:
    """Agencyレイヤーの全コンポーネントを生成し、DIに登録する。"""
    from iris.agency.bus import InternalBus
    from iris.agency.execution import (
        FlowExecutor,
        LLMGateway,
        ToolEngine,
    )
    from iris.agency.manager import AgencyManager
    from iris.agency.planning import PlanningManager, ProactiveScoring
    from iris.event.event_bus import EventBus
    from iris.io.session.manager import SessionManager
    from iris.kernel.debug_capture import DebugCapture
    from iris.llm.bridge import LLMBridge
    from iris.llm.capability import CapabilityChecker
    from iris.llm.prompt import Personality
    from iris.memory.long_term.stores import AgentsMdStore
    from iris.memory.manager import MemoryManager
    from iris.tools.registry import ToolRegistry

    event_bus = manager.resolve(EventBus)
    config = manager.config
    llm = manager.resolve(LLMBridge)
    memory = manager.resolve(MemoryManager)
    tool_registry = manager.resolve(ToolRegistry)
    session_mgr = manager.resolve(SessionManager)
    debug_capture = manager.resolve_optional(DebugCapture)

    internal_bus = InternalBus()

    personality = Personality(name=config.personality.name, prompt_file=config.personality.prompt_file)
    capability_checker = manager.resolve_optional(CapabilityChecker)
    if capability_checker is None:
        capability_checker = CapabilityChecker(config=config.model)

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

    return {
        "agency": agency,
        "planning": planning,
        "execution": execution,
        "pipeline": pipeline,
        "tool_exec": tool_exec,
    }
