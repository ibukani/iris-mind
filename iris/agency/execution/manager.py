from __future__ import annotations

import asyncio
from collections.abc import Callable
import logging
from typing import TYPE_CHECKING, Any

from iris.agency.bus import InternalBus, PlanDecided
from iris.agency.execution.modulation.coordinator import MonitorCoordinator
from iris.agency.execution.modulation.talkative import (
    apply_talkative_overrides,
    should_skip_proactive,
)
from iris.agency.execution.monitor import OutputMonitor
from iris.agency.execution.phases.runner import ExecutionRunner
from iris.agency.execution.pipeline import LLMPipeline
from iris.agency.execution.post_processor import PostProcessor
from iris.agency.inhibition import InhibitionController
from iris.event.event_bus import EventBus
from iris.event.event_types import InputReady
from iris.llm.interrupt_token import InterruptToken

if TYPE_CHECKING:
    from iris.memory.manager import MemoryManager

logger = logging.getLogger(__name__)


class ExecutionManager:
    def __init__(
        self,
        internal_bus: InternalBus,
        event_bus: EventBus,
        llm_pipeline: LLMPipeline,
        post_processor: PostProcessor,
        monitor: OutputMonitor | None = None,
        inhibition: InhibitionController | None = None,
        session_roles_getter: Callable[[], str] | None = None,
        memory: MemoryManager | None = None,
        messages: list[dict[str, Any]] | None = None,
    ) -> None:
        self._bus = internal_bus
        self._event_bus = event_bus
        self._monitor = monitor
        self._post_processor = post_processor
        self._memory = memory
        self._messages: list[dict[str, Any]] = messages if messages is not None else []
        self._interrupt_token: InterruptToken | None = None
        self._bg_tasks: set[asyncio.Task] = set()
        self._runner = ExecutionRunner(
            event_bus=event_bus,
            messages=self._messages,
            pipeline=llm_pipeline,
            post_processor=post_processor,
            monitor=monitor,
            inhibition=inhibition,
            session_roles_getter=session_roles_getter,
            memory=memory,
        )
        self._coordinator = MonitorCoordinator(event_bus, monitor, inhibition)
        self._bus.subscribe("PlanDecided", self._on_plan)
        self._event_bus.subscribe("InputReady", self._on_input_ready)

    def get_state(self) -> dict:
        state = self._post_processor.get_state()
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
            logger.info("ExecutionManager: cancelling current execution due to new user input")
            self._interrupt_token.cancel()

    def _on_plan(self, event: PlanDecided) -> None:
        plan = event.plan
        if self._monitor:
            if plan.get("content", ""):
                self._monitor.record_user_input()
            plan["talkative_degree"] = self._monitor.talkative_degree
            self._coordinator.sync_inhibition_state()
            self._coordinator.apply_emotion_to_monitor(plan)

        apply_talkative_overrides(plan)

        if should_skip_proactive(plan, self._monitor):
            logger.info(
                "ExecutionManager: suppressed proactive (talkative=%d), skipping LLM",
                plan.get("talkative_degree", 0),
            )
            return

        logger.info(
            "ExecutionManager: executing plan session=%s abbreviated=%s",
            plan.get("session_id"),
            plan.get("abbreviated"),
        )
        task = asyncio.create_task(self._runner.run(plan))
        self._bg_tasks.add(task)
        task.add_done_callback(self._bg_tasks.discard)

    def flush_memory(self) -> None:
        self._post_processor.flush_memory()
        if self._memory:
            self._memory.flush()

    def compact_context(self) -> str:
        return self._post_processor.compact_context()
