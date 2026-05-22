from __future__ import annotations

import asyncio
from collections.abc import Callable
import logging
from typing import TYPE_CHECKING, Any

from iris.agency.bus import InternalBus, PlanDecided
from iris.agency.execution.engine import ToolEngine
from iris.agency.execution.llm.gateway import LLMGateway
from iris.agency.execution.orchestrator import ExecutionOrchestrator
from iris.agency.execution.regulation.consolidator import Consolidator
from iris.agency.execution.regulation.feedback import FeedbackCoordinator
from iris.agency.execution.regulation.output_tracker import OutputTracker
from iris.agency.execution.regulation.talk_control import (
    apply_talkative_overrides,
    should_skip_proactive,
)
from iris.agency.execution.state import ExecutionState
from iris.agency.inhibition import InhibitionController
from iris.event.event_bus import EventBus
from iris.event.event_types import InputReady
from iris.llm.capability_checker import CapabilityChecker
from iris.llm.interrupt_token import InterruptToken

if TYPE_CHECKING:
    from iris.memory.manager import MemoryManager

logger = logging.getLogger(__name__)


class FlowExecutor:
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
        messages: list[dict[str, Any]] | None = None,
    ) -> None:
        self._bus = internal_bus
        self._event_bus = event_bus
        self._monitor = monitor
        self._consolidator = consolidator
        self._memory = memory
        self._messages: list[dict[str, Any]] = messages if messages is not None else []
        self._interrupt_token: InterruptToken | None = None
        self._bg_tasks: set[asyncio.Task] = set()

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
        self._event_bus.subscribe("InputReady", self._on_input_ready)

    def get_state(self) -> dict:
        state = self._consolidator.get_state()
        state["msg_count"] = len(self._messages)
        state["talkative_degree"] = self._monitor.talkative_degree if self._monitor else 0
        return state

    def _on_input_ready(self, event: InputReady) -> None:
        context = event.context or {}
        if (
            not context.get("from_timer")
            and "system_event" not in context
            and self._interrupt_token
            and not self._interrupt_token.is_cancelled
        ):
            logger.info("FlowExecutor: cancelling current execution due to new user input")
            self._interrupt_token.cancel()

    def _on_plan(self, event: PlanDecided) -> None:
        plan = event.plan
        if self._monitor:
            if plan.get("content", ""):
                self._monitor.record_user_input()
            plan["talkative_degree"] = self._monitor.talkative_degree

        apply_talkative_overrides(plan)

        if should_skip_proactive(plan, self._monitor):
            logger.info(
                "FlowExecutor: suppressed proactive (talkative=%d), skipping LLM",
                plan.get("talkative_degree", 0),
            )
            return

        logger.info(
            "FlowExecutor: executing plan session=%s abbreviated=%s",
            plan.get("session_id"),
            plan.get("abbreviated"),
        )
        task = asyncio.create_task(self._run_graph(plan))
        self._bg_tasks.add(task)
        task.add_done_callback(self._bg_tasks.discard)

    async def _run_graph(self, plan: dict[str, Any]) -> None:
        self._interrupt_token = InterruptToken()
        self._graph.set_callbacks(
            interrupt_token=self._interrupt_token,
        )

        state: ExecutionState = {
            "plan": plan,
            "messages": self._messages,
            "response_text": "",
            "tool_iterations": 0,
            "interrupted": False,
            "error": None,
            "completed": False,
        }

        try:
            result = await self._graph.ainvoke(state)
            self._messages[:] = result.get("messages", [])
        except Exception as e:
            logger.exception("Graph execution failed")
            self._messages.append({"role": "system", "content": f"[Execution Error: {e}]"})
        finally:
            self._interrupt_token = None

    def flush_memory(self) -> None:
        self._consolidator.flush_memory()
        if self._memory:
            self._memory.flush()

    def compact_context(self) -> str:
        return self._consolidator.compact_context()
