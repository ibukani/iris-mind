from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from langchain_core.messages import BaseMessage, SystemMessage

from iris.agency.bus import InternalBus, PlanDecided
from iris.agency.execution.builders import build_execution_state, should_skip_plan
from iris.agency.execution.engine import ToolEngine
from iris.agency.execution.llm.gateway import LLMGateway
from iris.agency.execution.orchestrator import ExecutionOrchestrator
from iris.agency.execution.regulation.consolidator import Consolidator
from iris.agency.execution.regulation.feedback import FeedbackCoordinator
from iris.agency.execution.regulation.output_tracker import OutputTracker
from iris.agency.execution.worker import AsyncWorker
from iris.agency.inhibition import InhibitionController
from iris.agency.planning.models import Plan
from iris.event.event_bus import EventBus
from iris.event.event_types import InterruptEvent
from iris.llm.capability import CapabilityChecker
from iris.llm.interrupt_token import InterruptToken

if TYPE_CHECKING:
    from iris.memory.manager import MemoryManager

from loguru import logger


class FlowExecutor(AsyncWorker):
    def __init__(
        self,
        internal_bus: InternalBus,
        event_bus: EventBus,
        llm_pipeline: LLMGateway,
        consolidator: Consolidator,
        tool_executor: ToolEngine | None = None,
        monitor: OutputTracker | None = None,
        inhibition: InhibitionController | None = None,
        session_roles_getter: Callable[[], str] | None = None,
        memory: MemoryManager | None = None,
        capability_checker: CapabilityChecker | None = None,
        messages: list[BaseMessage] | None = None,
    ) -> None:
        super().__init__(name="executor-worker")

        self._bus = internal_bus
        self._event_bus = event_bus
        self._monitor = monitor
        self._inhibition = inhibition
        self._consolidator = consolidator
        self._memory = memory
        self._messages: list[BaseMessage] = messages if messages is not None else []
        self._interrupt_token: InterruptToken | None = None

        coordinator = FeedbackCoordinator(event_bus, monitor, inhibition)

        self._graph = ExecutionOrchestrator(
            pipeline=llm_pipeline,
            tool_executor=tool_executor,
            consolidator=consolidator,
            monitor=monitor,
            coordinator=coordinator,
            inhibition=inhibition,
            event_bus=event_bus,
            memory=memory,
            session_roles_getter=session_roles_getter,
            capability_checker=capability_checker,
        )

        self._bus.subscribe("PlanDecided", self._on_plan)
        self._event_bus.subscribe("InterruptEvent", self._on_interrupt)

    def get_state(self) -> dict:
        state = self._consolidator.get_state()
        state["msg_count"] = len(self._messages)
        state["talkative_degree"] = self._monitor.talkative_degree if self._monitor else 0
        return state

    def _on_interrupt(self, event: InterruptEvent) -> None:
        if self._interrupt_token and not self._interrupt_token.is_cancelled:
            logger.info("FlowExecutor: cancelling current execution due to interrupt")
            self._interrupt_token.cancel()

    def _on_plan(self, event: PlanDecided) -> None:
        plan = event.plan
        if self._monitor and plan.content:
            self._monitor.record_user_input()

        if should_skip_plan(plan, self._monitor):
            degree = self._monitor.talkative_degree if self._monitor else 0
            logger.info(
                "FlowExecutor: suppressed proactive (talkative={}), skipping LLM",
                degree,
            )
            return

        logger.info(
            "FlowExecutor: queueing plan session={}",
            plan.session_id,
        )
        self.enqueue(plan)

    async def process(self, plan: Plan) -> None:  # type: ignore[override]
        self._interrupt_token = InterruptToken()
        self._graph.set_callbacks(
            interrupt_token=self._interrupt_token,
        )

        state = build_execution_state(plan, self._messages, self._monitor, self._inhibition)

        try:
            result = await self._graph.ainvoke(state)
            self._messages[:] = result.get("messages", [])
        except Exception as e:
            logger.exception("Graph execution failed")
            self._messages.append(SystemMessage(content=f"[Execution Error: {e}]"))
        finally:
            self._interrupt_token = None

    def shutdown(self, timeout: float = 5.0) -> None:
        self.flush_memory()
        super().shutdown(timeout=timeout)

    def flush_memory(self) -> None:
        self._consolidator.flush_memory()
        if self._memory:
            self._memory.flush()

    def compact_context(self) -> str:
        return self._consolidator.compact_context()
