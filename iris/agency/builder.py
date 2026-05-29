"""Agencyレイヤーのコンポーネント組み立て。"""

from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict

if TYPE_CHECKING:
    from iris.agency.execution import FlowExecutor, LLMGateway, ToolEngine
    from iris.agency.inhibition import InhibitionManager
    from iris.agency.internal_bus import InternalBus
    from iris.agency.manager import AgencyManager
    from iris.agency.planning import (
        PlanningManager,
        ProactivePlanStrategy,
        ResponsePlanStrategy,
    )
    from iris.agency.planning.decisions import ProactiveJudge
    from iris.kernel.manager import PluginManager


class AgencyComponents(TypedDict):
    agency: AgencyManager
    planning: PlanningManager
    execution: FlowExecutor
    pipeline: LLMGateway
    tool_exec: ToolEngine
    internal_bus: InternalBus
    proactive_judge: ProactiveJudge
    proactive_strategy: ProactivePlanStrategy
    response_strategy: ResponsePlanStrategy
    inhibition: InhibitionManager


def build_agency(manager: PluginManager) -> AgencyComponents:
    """Agencyレイヤーの全コンポーネントを生成し、DIに登録する。"""
    from iris.agency.execution import (
        FlowExecutor,
        LLMGateway,
        ToolEngine,
    )
    from iris.agency.inhibition import InhibitionManager
    from iris.agency.internal_bus import InternalBus
    from iris.agency.manager import AgencyManager
    from iris.agency.planning import (
        ContextHintBuilder,
        PlanningManager,
        ProactivePlanStrategy,
        ProactiveScorer,
        QuestionGenerator,
        ResponsePlanStrategy,
    )
    from iris.agency.planning.decisions import ProactiveJudge
    from iris.event.event_bus import EventBus
    from iris.io.session.manager import SessionManager
    from iris.kernel.debug_capture import DebugCapture
    from iris.llm.bridge import LLMBridge
    from iris.llm.capability import CapabilityChecker
    from iris.llm.prompt import Personality
    from iris.memory.long_term.stores import AgentsMdStore
    from iris.memory.manager import MemoryManager
    from iris.memory.user_store import UserStore
    from iris.tools.registry import ToolRegistry

    event_bus = manager.resolve(EventBus)
    config = manager.config
    session_mgr = manager.resolve(SessionManager)

    inhibition = InhibitionManager(
        config=config.inhibition,
        session_getter=session_mgr.has_active_sessions,
    )
    llm = manager.resolve(LLMBridge)
    memory = manager.resolve(MemoryManager)
    tool_registry = manager.resolve(ToolRegistry)
    debug_capture = manager.resolve_optional(DebugCapture)

    internal_bus = InternalBus()

    personality = Personality(name=config.personality.name, prompt_file=config.personality.prompt_file)
    capability_checker = manager.resolve_optional(CapabilityChecker)
    if capability_checker is None:
        capability_checker = CapabilityChecker(config=config.model)

    agents_md_store = AgentsMdStore(path=config.memory.agents_md_path, max_bytes=config.memory.agents_md_max_bytes)

    user_store = manager.resolve_optional(UserStore)

    pipeline = LLMGateway(
        llm=llm,
        model_config=config.model,
        personality=personality,
        agents_md_store=agents_md_store,
        memory=memory,
        capability_checker=capability_checker,
        debug_capture=debug_capture,
        prompts_dir=config.personality.node_prompts_dir,
        user_store=user_store,
    )

    tool_exec = ToolEngine(registry=tool_registry)

    execution = FlowExecutor(
        event_bus=event_bus,
        llm_pipeline=pipeline,
        tool_executor=tool_exec,
        session_roles_getter=session_mgr.get_sessions_summary,
        memory=memory,
        capability_checker=CapabilityChecker(config=config.model),
        inhibition=inhibition,
        tts_mora_per_sec=config.inhibition.tts_mora_per_sec,
    )

    scoring = ProactiveScorer(config=config.proactive, memory=memory)

    context_builder = ContextHintBuilder(memory=memory)
    question_gen = QuestionGenerator(llm=llm) if llm else None

    proactive_judge = ProactiveJudge(
        scoring=scoring,
        config=config.proactive,
        context_builder=context_builder,
    )
    proactive_strategy = ProactivePlanStrategy(question_gen=question_gen)
    response_strategy = ResponsePlanStrategy(
        config=config.proactive,
        context_builder=context_builder,
    )

    planning = PlanningManager(
        internal_bus=internal_bus,
        proactive_judge=proactive_judge,
        proactive_strategy=proactive_strategy,
        response_strategy=response_strategy,
    )

    agency = AgencyManager(planning=planning, execution=execution, inhibition=inhibition)

    manager.provide(InhibitionManager, inhibition)

    return {
        "agency": agency,
        "planning": planning,
        "execution": execution,
        "pipeline": pipeline,
        "tool_exec": tool_exec,
        "internal_bus": internal_bus,
        "proactive_judge": proactive_judge,
        "proactive_strategy": proactive_strategy,
        "response_strategy": response_strategy,
        "inhibition": inhibition,
    }
