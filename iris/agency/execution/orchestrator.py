from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from langgraph.graph import END, StateGraph

from iris.agency.execution.node_types import NODE_TYPES
from iris.agency.execution.nodes.finalize import FinalizeNode
from iris.agency.execution.nodes.general_chat import GeneralChatNode
from iris.agency.execution.nodes.general_task import GeneralTaskNode
from iris.agency.execution.nodes.post_process import PostProcessNode
from iris.agency.execution.nodes.setup import SetupNode
from iris.agency.execution.nodes.tool_run import ToolRunNode
from iris.agency.execution.state import DynamicState, ExecutionState
from iris.llm.interrupt_token import InterruptToken

if TYPE_CHECKING:
    from iris.agency.execution.engine import ToolEngine
    from iris.agency.execution.llm.gateway import LLMGateway
    from iris.agency.execution.regulation.consolidator import Consolidator
    from iris.agency.execution.regulation.feedback import FeedbackCoordinator
    from iris.agency.execution.regulation.output_tracker import OutputTracker
    from iris.agency.inhibition import InhibitionController
    from iris.event.event_bus import EventBus
    from iris.llm.capability import CapabilityChecker
    from iris.memory.manager import MemoryManager

from loguru import logger


def _with_state_trace(name: str, node_fn: Any) -> Any:
    async def wrapped(state: ExecutionState) -> dict[str, Any] | None:
        raw: dict[str, Any] = state  # type: ignore[assignment]
        keys = [k for k in raw if k != "messages"]
        before = {k: repr(raw[k]) for k in keys}
        result: dict[str, Any] | None = await node_fn(state)
        after = {k: repr(raw[k]) for k in keys}
        changed = {k: {"before": before[k], "after": after[k]} for k in keys if before[k] != after[k]}
        if changed:
            logger.debug("NODE[{}] state diff: {}", name, changed)
        if result is not None:
            logger.debug("NODE[{}] return: {}", name, {k: repr(v) for k, v in result.items()})
        return result

    return wrapped


class ExecutionOrchestrator:
    def __init__(
        self,
        pipeline: LLMGateway,
        tool_executor: ToolEngine | None = None,
        consolidator: Consolidator | None = None,
        monitor: OutputTracker | None = None,
        coordinator: FeedbackCoordinator | None = None,
        inhibition: InhibitionController | None = None,
        event_bus: EventBus | None = None,
        memory: MemoryManager | None = None,
        session_roles_getter: Callable[[], str] | None = None,
        capability_checker: CapabilityChecker | None = None,
    ) -> None:
        self._dynamic = DynamicState()

        self._prepare = SetupNode(
            pipeline=pipeline,
            event_bus=event_bus,
            memory=memory,
            consolidator=consolidator,
            session_roles_getter=session_roles_getter,
            dynamic=self._dynamic,
        )
        self._general_chat = GeneralChatNode(
            pipeline=pipeline,
            tool_executor=tool_executor,
            capability_checker=capability_checker,
            dynamic=self._dynamic,
            event_bus=event_bus,
            memory=memory,
        )
        self._general_task = GeneralTaskNode(
            pipeline=pipeline,
            tool_executor=tool_executor,
            capability_checker=capability_checker,
            dynamic=self._dynamic,
            event_bus=event_bus,
            memory=memory,
            limbic=None,
        )
        self._execute_tools_node = ToolRunNode(
            tool_executor=tool_executor,
            consolidator=consolidator,
        )
        self._finalize = FinalizeNode(
            event_bus=event_bus,
            memory=memory,
            consolidator=consolidator,
            monitor=monitor,
            coordinator=coordinator,
        )
        self._post_process = PostProcessNode(
            consolidator=consolidator,
        )

        self._compiled_graph = self._build_graph()

    def set_callbacks(
        self,
        on_token: Callable[[str], None] | None = None,
        interrupt_token: InterruptToken | None = None,
    ) -> None:
        self._dynamic.on_token = on_token
        self._dynamic.interrupt_token = interrupt_token

    async def ainvoke(self, state: ExecutionState) -> dict[str, Any]:
        result: dict[str, Any] = await self._compiled_graph.ainvoke(state)
        return result

    def _build_graph(self) -> Any:
        builder = StateGraph(ExecutionState)

        builder.add_node("prepare_context", _with_state_trace("prepare_context", self._prepare))
        builder.add_node("general_chat", _with_state_trace("general_chat", self._general_chat))
        builder.add_node("general_task", _with_state_trace("general_task", self._general_task))
        builder.add_node("execute_tools", _with_state_trace("execute_tools", self._execute_tools_node))
        builder.add_node("finalize", _with_state_trace("finalize", self._finalize))
        builder.add_node("post_process", _with_state_trace("post_process", self._post_process))

        builder.set_entry_point("prepare_context")
        builder.add_edge("prepare_context", "general_chat")

        for llm_node in ("general_chat", "general_task"):
            builder.add_conditional_edges(
                llm_node,
                self._route_after_llm,
                {
                    "general_chat": "general_chat",
                    "general_task": "general_task",
                    "execute_tools": "execute_tools",
                    "finalize": "finalize",
                },
            )

        builder.add_conditional_edges(
            "execute_tools",
            self._route_after_tools,
            {"general_chat": "general_chat", "general_task": "general_task", "finalize": "finalize"},
        )

        builder.add_conditional_edges(
            "finalize",
            self._route_after_finalize,
            {"post_process": "post_process", "__end__": END},
        )
        builder.add_edge("post_process", END)

        return builder.compile()

    @staticmethod
    def _route_after_llm(state: ExecutionState) -> str:
        if state.get("interrupted") or state.get("error"):
            return "finalize"

        messages = state.get("messages", [])
        if not messages:
            return "finalize"

        last = messages[-1]
        tcs = getattr(last, "tool_calls", None) or []

        for tc in tcs:
            name = tc["name"]

            if name == "general_chat":
                state["chain_depth"] += 1
                state["current_node_type"] = "general_chat"
                logger.debug("ROUTE: general_chat (chain depth={})", state["chain_depth"])
                return "general_chat"

            if name == "general_task":
                state["chain_depth"] = 0
                state["current_node_type"] = "general_task"
                nt = NODE_TYPES["general_task"]
                state["current_level_idx"] = nt.available_levels.index(nt.entry_level)
                logger.debug("ROUTE: general_task")
                return "general_task"

            if name == "deep_task":
                state["chain_depth"] = 0
                nt = NODE_TYPES.get(state["current_node_type"]) or NODE_TYPES["general_task"]
                next_idx = state["current_level_idx"] + 1
                if next_idx < len(nt.available_levels):
                    state["current_level_idx"] = next_idx
                    logger.debug(
                        "ROUTE: deep_task level={}",
                        nt.available_levels[state["current_level_idx"]],
                    )
                return state["current_node_type"]

            if name == "finish":
                logger.debug("ROUTE: finish")
                return "finalize"

        if tcs:
            return "execute_tools"

        return "finalize"

    @staticmethod
    def _route_after_tools(state: ExecutionState) -> str:
        plan = state["plan"]
        max_iters = plan.get("max_tool_iterations", 5)
        if state.get("tool_iterations", 0) >= max_iters:
            logger.debug("Tool iteration limit reached ({})", max_iters)
            return "finalize"
        return state["current_node_type"]

    @staticmethod
    def _route_after_finalize(state: ExecutionState) -> str:
        plan = state["plan"]
        run_reflexion = plan.get("run_reflexion", False)
        run_compression = plan.get("run_compression", False)
        if run_reflexion or run_compression:
            return "post_process"
        return "__end__"
