from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from langgraph.graph import END, StateGraph

from iris.agency.execution.nodes.finalize import FinalizeNode
from iris.agency.execution.nodes.llm_call import LLMCallNode
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
        self._generate = LLMCallNode(
            pipeline=pipeline,
            tool_executor=tool_executor,
            capability_checker=capability_checker,
            dynamic=self._dynamic,
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

        builder.add_node("prepare_context", self._prepare)
        builder.add_node("llm_generate", self._generate)
        builder.add_node("execute_tools", self._execute_tools_node)
        builder.add_node("finalize", self._finalize)
        builder.add_node("post_process", self._post_process)

        builder.set_entry_point("prepare_context")
        builder.add_edge("prepare_context", "llm_generate")
        builder.add_conditional_edges(
            "llm_generate",
            self._router_after_generate,
            {"execute_tools": "execute_tools", "finalize": "finalize"},
        )
        builder.add_conditional_edges(
            "execute_tools",
            self._router_after_tools,
            {"llm_generate": "llm_generate", "finalize": "finalize"},
        )
        builder.add_conditional_edges(
            "finalize",
            self._router_after_finalize,
            {"post_process": "post_process", "__end__": END},
        )
        builder.add_edge("post_process", END)

        return builder.compile()

    @staticmethod
    def _router_after_generate(state: ExecutionState) -> str:
        if state.get("interrupted") or state.get("error"):
            return "finalize"
        messages = state.get("messages", [])
        if messages and getattr(messages[-1], "tool_calls", None):
            return "execute_tools"
        return "finalize"

    @staticmethod
    def _router_after_tools(state: ExecutionState) -> str:
        plan = state["plan"]
        max_iters = plan.get("max_tool_iterations", 3)
        if state.get("tool_iterations", 0) >= max_iters:
            logger.debug("Tool iteration limit reached (%d)", max_iters)
            return "finalize"
        return "llm_generate"

    @staticmethod
    def _router_after_finalize(state: ExecutionState) -> str:
        plan = state["plan"]
        run_reflexion = plan.get("run_reflexion", False)
        run_compression = plan.get("run_compression", False)
        if run_reflexion or run_compression:
            return "post_process"
        return "__end__"
