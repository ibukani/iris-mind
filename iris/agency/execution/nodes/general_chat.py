from __future__ import annotations

from typing import TYPE_CHECKING

from langchain_core.messages import BaseMessage

from iris.agency.execution.nodes.base import BaseLLMNode

if TYPE_CHECKING:
    from iris.agency.execution.state import ExecutionState
    from iris.agency.task_level import TaskLevel


class GeneralChatNode(BaseLLMNode):
    node_type_name = "general_chat"

    def _build_prompt(self, state: ExecutionState, level: TaskLevel) -> list[BaseMessage] | None:
        return None
