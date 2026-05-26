from __future__ import annotations

from typing import TYPE_CHECKING

from iris.agency.execution.nodes.base import BaseLLMNode

if TYPE_CHECKING:
    from iris.agency.execution.engine import ToolEngine
    from iris.agency.execution.llm.gateway import LLMGateway
    from iris.agency.execution.models import DynamicState
    from iris.event.event_bus import EventBus
    from iris.llm.capability import CapabilityChecker
    from iris.memory.manager import MemoryManager


class GeneralTaskNode(BaseLLMNode):
    @property
    def node_type_name(self) -> str:
        return "general_task"

    def __init__(
        self,
        pipeline: LLMGateway,
        tool_executor: ToolEngine | None = None,
        capability_checker: CapabilityChecker | None = None,
        dynamic: DynamicState | None = None,
        event_bus: EventBus | None = None,
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
