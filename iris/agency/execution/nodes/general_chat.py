from __future__ import annotations

from typing import TYPE_CHECKING, Any

from iris.agency.execution.models import ExecutionState
from iris.agency.execution.nodes.base import BaseLLMNode
from iris.agency.planning.models import Plan
from iris.agency.task_level import TaskLevel

if TYPE_CHECKING:
    from iris.agency.execution.engine import ToolEngine
    from iris.agency.execution.llm.gateway import LLMGateway
    from iris.agency.execution.models import DynamicState
    from iris.event.event_bus import EventBus
    from iris.llm.capability import CapabilityChecker
    from iris.memory.manager import MemoryManager


class GeneralChatNode(BaseLLMNode):
    @property
    def node_type_name(self) -> str:
        return "general_chat"

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

    def _build_chat_params(
        self,
        state: ExecutionState,
        level: TaskLevel,
        plan: Plan,
    ) -> dict[str, Any]:
        return {
            "model_role": "low",
            "temperature": 0.85 if level.temperature is None else level.temperature,
            "max_tokens": 256,
            "priority": level.priority,
            "show_thinking": False,
            "modulation": plan.modulation,
        }
