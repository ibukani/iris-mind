from __future__ import annotations

from typing import TYPE_CHECKING

from langchain_core.messages import BaseMessage

from iris.agency.execution.nodes.base import BaseLLMNode

if TYPE_CHECKING:
    from iris.agency.execution.engine import ToolEngine
    from iris.agency.execution.llm.gateway import LLMGateway
    from iris.agency.execution.state import DynamicState, ExecutionState
    from iris.agency.task_level import TaskLevel
    from iris.event.event_bus import EventBus
    from iris.limbic.manager import LimbicManager
    from iris.llm.capability import CapabilityChecker
    from iris.memory.manager import MemoryManager


class GeneralTaskNode(BaseLLMNode):
    node_type_name = "general_task"

    def __init__(
        self,
        pipeline: LLMGateway,
        tool_executor: ToolEngine | None = None,
        capability_checker: CapabilityChecker | None = None,
        dynamic: DynamicState | None = None,
        event_bus: EventBus | None = None,
        limbic: LimbicManager | None = None,
        memory: MemoryManager | None = None,
    ) -> None:
        super().__init__(
            pipeline=pipeline,
            tool_executor=tool_executor,
            capability_checker=capability_checker,
            dynamic=dynamic,
            event_bus=event_bus,
            memory=memory,
        )
        self._limbic = limbic

    def _build_prompt(self, state: ExecutionState, level: TaskLevel) -> list[BaseMessage] | None:
        return None
