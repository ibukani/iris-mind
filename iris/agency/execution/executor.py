from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from langchain_core.messages import BaseMessage, SystemMessage

from iris.agency.execution.builder import build_execution_state
from iris.agency.execution.engine import ToolEngine
from iris.agency.execution.llm.gateway import LLMGateway
from iris.agency.execution.orchestrator import ExecutionOrchestrator
from iris.agency.execution.worker import AsyncWorker
from iris.agency.inhibition import InhibitionManager
from iris.agency.planning.models import Plan
from iris.event.event_bus import EventBus
from iris.llm.capability import CapabilityChecker
from iris.llm.interrupt_token import InterruptToken

if TYPE_CHECKING:
    from iris.memory.manager import MemoryManager

from loguru import logger


class FlowExecutor(AsyncWorker):
    def __init__(
        self,
        event_bus: EventBus,
        llm_pipeline: LLMGateway,
        tool_executor: ToolEngine | None = None,
        session_roles_getter: Callable[[], str] | None = None,
        memory: MemoryManager | None = None,
        capability_checker: CapabilityChecker | None = None,
        inhibition: InhibitionManager | None = None,
        messages: list[BaseMessage] | None = None,
        tts_mora_per_sec: float = 6.5,
    ) -> None:
        super().__init__(name="executor-worker")

        self._event_bus = event_bus
        self._memory = memory
        self._inhibition = inhibition
        self._tts_mora_per_sec = tts_mora_per_sec
        self._messages: list[BaseMessage] = messages if messages is not None else []
        self._interrupt_token: InterruptToken | None = None

        self._graph = ExecutionOrchestrator(
            pipeline=llm_pipeline,
            tool_executor=tool_executor,
            event_bus=event_bus,
            memory=memory,
            session_roles_getter=session_roles_getter,
            capability_checker=capability_checker,
        )

    def get_state(self) -> dict:
        return {
            "msg_count": len(self._messages),
        }

    def cancel_execution(self) -> None:
        if self._interrupt_token and not self._interrupt_token.is_cancelled:
            logger.info("FlowExecutor: cancelling current execution")
            self._interrupt_token.cancel()

    async def process(self, plan: Plan) -> None:  # type: ignore[override]
        if self._inhibition:
            decision = self._inhibition.acquire_execution()
            if not decision.allow:
                logger.warning("FlowExecutor: execution denied by gate reason={}", decision.reason)
                return

        self._interrupt_token = InterruptToken()
        self._graph.set_callbacks(
            interrupt_token=self._interrupt_token,
        )

        state = build_execution_state(plan, self._messages)

        try:
            before = len(self._messages)
            result = await self._graph.ainvoke(state)
            self._messages[:] = result.get("messages", [])
        except Exception as e:
            logger.exception("Graph execution failed")
            self._messages.append(SystemMessage(content=f"[Execution Error: {e}]"))
        finally:
            self._interrupt_token = None
            if self._inhibition:
                self._inhibition.release_execution()
                new_ai_content = "".join(
                    m.content for m in self._messages[before:]
                    if getattr(m, "type", None) == "ai" and isinstance(m.content, str)
                )
                if new_ai_content:
                    self._inhibition.suppress("speaking", len(new_ai_content) / self._tts_mora_per_sec)

    def shutdown(self, timeout: float = 5.0) -> None:
        if self._memory:
            self._memory.flush()
        super().shutdown(timeout=timeout)

    def flush_memory(self) -> None:
        if self._memory:
            self._memory.flush()
