from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

from langchain_core.messages import SystemMessage

if TYPE_CHECKING:
    from iris.limbic.manager import LimbicManager
    from iris.llm.prompt import Personality
    from iris.memory.long_term.stores import AgentsMdStore
    from iris.memory.manager import MemoryManager
    from iris.memory.persona_profile import PersonaProfile


class ProfileBuilder:
    """人格・状態・静的情報の SystemMessage を構築する。

    Dual SystemMessage の [0] として使われる Profile を担当。
    """

    def __init__(
        self,
        personality: Personality,
        agents_md_store: AgentsMdStore | None = None,
        persona_profile: PersonaProfile | None = None,
        memory: MemoryManager | None = None,
        limbic: LimbicManager | None = None,
        governance_principles: str = "",
    ) -> None:
        self._personality = personality
        self._agents_md_store = agents_md_store
        self._persona_profile = persona_profile
        self._memory = memory
        self._limbic = limbic
        self._governance_principles = governance_principles

    def build(
        self,
        response_style: str = "",
        session_roles_summary: str = "",
        current_user_identity: str = "",
    ) -> SystemMessage:
        """Profile SystemMessage を構築する。"""
        agents_md = self._load_agents_md()
        speech_style = self._persona_profile.get_speech_style() if self._persona_profile else ""
        personality_traits = self._persona_profile.get_traits() if self._persona_profile else ""
        user_prefs = self._build_user_preferences_section()

        current_state = ""
        if self._persona_profile:
            has_traits_in_tpl = "{personality_traits}" in self._personality.system_prompt_template
            has_speech_in_tpl = "{speech_style}" in self._personality.system_prompt_template
            if not has_traits_in_tpl and not has_speech_in_tpl:
                current_state = self._persona_profile.get_current_state_section()

        base = self._personality.build_system_prompt(
            agents_md_content=agents_md,
            user_preferences=user_prefs,
            session_roles=session_roles_summary,
            response_style=response_style,
            speech_style=speech_style,
            personality_traits=personality_traits,
            governance_principles=self._governance_principles,
        )

        parts: list[str] = [base]
        parts.append(f"## 現在日時\n{self._build_time_string()}")

        if self._limbic:
            mood_desc = self._limbic.describe_mood() or "落ち着いた状態。特に強い感情はないよ。"
            parts.append(f"## 現在の気分\n{mood_desc}")

        if current_state:
            parts.append(current_state)

        if current_user_identity:
            parts.append(f"## 現在の会話相手\n{current_user_identity}")

        return SystemMessage(content="\n\n".join(parts))

    def _load_agents_md(self) -> str:
        return self._agents_md_store.load() if self._agents_md_store else ""

    def _build_user_preferences_section(self) -> str:
        prefs_list = self._memory.get_user_preferences() if self._memory else []
        seen: set[str] = set()
        unique_prefs: list[str] = []
        for p in prefs_list:
            c = p.get("content", "").strip()
            if c and c not in seen:
                seen.add(c)
                unique_prefs.append(f"- {c}")
        return "\n".join(unique_prefs)

    @staticmethod
    def _build_time_string() -> str:
        dt_now = datetime.datetime.now()
        weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        return f"{dt_now.strftime('%Y-%m-%d %H:%M:%S')} ({weekdays[dt_now.weekday()]})"
