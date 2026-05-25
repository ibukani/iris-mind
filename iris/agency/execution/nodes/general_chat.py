from __future__ import annotations

from typing import TYPE_CHECKING, Any

from langchain_core.messages import BaseMessage, SystemMessage

from iris.agency.execution.nodes.base import BaseLLMNode

if TYPE_CHECKING:
    from iris.agency.execution.state import ExecutionState
    from iris.agency.task_level import TaskLevel


class GeneralChatNode(BaseLLMNode):
    node_type_name = "general_chat"

    def _build_system_prompt(
        self,
        state: ExecutionState,
        level: TaskLevel,
        plan: dict[str, Any],
    ) -> list[BaseMessage] | None:
        parts = ["You are Iris, a helpful AI assistant. Answer concisely."]

        if self._memory:
            turns = self._memory.short_term.get_recent_turns(3)
            if turns:
                ctx = "\n".join(
                    f"{t['role']}: {t['content']}" for t in turns if t.get("content")
                )
                if ctx:
                    parts.append("## 直近の会話\n" + ctx)

        return [SystemMessage(content="\n\n".join(parts))]
