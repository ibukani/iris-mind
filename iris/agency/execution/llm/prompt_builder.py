from __future__ import annotations

from typing import TYPE_CHECKING, Any

from langchain_core.messages import BaseMessage

from iris.agency.execution.llm.node_prompt_factory import NodePromptFactory
from iris.agency.execution.llm.profile_builder import ProfileBuilder

if TYPE_CHECKING:
    from iris.llm.prompt import Personality
    from iris.memory.long_term.stores import AgentsMdStore
    from iris.memory.manager import MemoryManager


class SystemPromptBuilder:
    def __init__(
        self,
        personality: Personality,
        agents_md_store: AgentsMdStore | None = None,
        persona_profile: Any | None = None,
        memory: MemoryManager | None = None,
        governance_principles: str = "",
        prompts_dir: str | None = None,
    ) -> None:
        self._profile_builder = ProfileBuilder(
            personality=personality,
            agents_md_store=agents_md_store,
            persona_profile=persona_profile,
            memory=memory,
            governance_principles=governance_principles,
        )
        self._node_factory = NodePromptFactory(prompts_dir=prompts_dir)

    def build(
        self,
        node_type: str = "general_task",
        context_hint: str = "",
        response_style: str = "",
        session_roles_summary: str = "",
        current_nickname: str = "",
        include_profile: bool = True,
        chaos_level: float = 0.0,
        room_id: str = "",
    ) -> list[BaseMessage]:
        msgs: list[BaseMessage] = []

        if include_profile:
            msgs.append(
                self._profile_builder.build(
                    response_style=response_style,
                    session_roles_summary=session_roles_summary,
                    current_nickname=current_nickname,
                    room_id=room_id,
                ),
            )

        msgs.append(
            self._node_factory.build(
                node_type=node_type,
                context_hint=context_hint,
                chaos_level=chaos_level,
            ),
        )

        return msgs
