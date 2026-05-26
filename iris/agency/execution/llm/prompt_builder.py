from __future__ import annotations

from typing import TYPE_CHECKING

from langchain_core.messages import BaseMessage

from iris.agency.execution.llm.node_prompt_factory import NodePromptFactory
from iris.agency.execution.llm.profile_builder import ProfileBuilder

if TYPE_CHECKING:
    from iris.limbic.manager import LimbicManager
    from iris.llm.prompt import Personality
    from iris.memory.long_term.stores import AgentsMdStore
    from iris.memory.manager import MemoryManager
    from iris.memory.persona_profile import PersonaProfile


class SystemPromptBuilder:
    """Profile + NodePrompt の 2 つの SystemMessage を構築する。

    Personality テンプレート + 動的データ → Profile SystemMessage
    ノード固有指示 + タスクコンテキスト → NodePrompt SystemMessage
    これらを結合して list[BaseMessage] として返す。
    """

    def __init__(
        self,
        personality: Personality,
        agents_md_store: AgentsMdStore | None = None,
        persona_profile: PersonaProfile | None = None,
        memory: MemoryManager | None = None,
        limbic: LimbicManager | None = None,
        governance_principles: str = "",
        prompts_dir: str | None = None,
    ) -> None:
        self._profile_builder = ProfileBuilder(
            personality=personality,
            agents_md_store=agents_md_store,
            persona_profile=persona_profile,
            memory=memory,
            limbic=limbic,
            governance_principles=governance_principles,
        )
        self._node_factory = NodePromptFactory(prompts_dir=prompts_dir)

    def build(
        self,
        node_type: str = "general_task",
        context_hint: str = "",
        response_style: str = "",
        session_roles_summary: str = "",
        current_user_identity: str = "",
        situation: str = "",
        recent_turns: str = "",
        include_profile: bool = True,
    ) -> list[BaseMessage]:
        msgs: list[BaseMessage] = []

        if include_profile:
            msgs.append(
                self._profile_builder.build(
                    response_style=response_style,
                    session_roles_summary=session_roles_summary,
                    current_user_identity=current_user_identity,
                )
            )

        msgs.append(
            self._node_factory.build(
                node_type=node_type,
                context_hint=context_hint,
                situation=situation,
                recent_turns=recent_turns,
            )
        )

        return msgs
