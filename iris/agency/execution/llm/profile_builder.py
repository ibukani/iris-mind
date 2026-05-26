from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, Any

from langchain_core.messages import SystemMessage

if TYPE_CHECKING:
    from iris.llm.prompt import Personality
    from iris.memory.long_term.stores import AgentsMdStore
    from iris.memory.manager import MemoryManager


class ProfileBuilder:
    def __init__(
        self,
        personality: Personality,
        agents_md_store: AgentsMdStore | None = None,
        persona_profile: Any | None = None,
        memory: MemoryManager | None = None,
        governance_principles: str = "",
    ) -> None:
        self._personality = personality
        self._agents_md_store = agents_md_store
        self._persona_profile = persona_profile
        self._memory = memory
        self._governance_principles = governance_principles

    def build(
        self,
        response_style: str = "",
        session_roles_summary: str = "",
        current_user_identity: str = "",
    ) -> SystemMessage:
        agents_md = self._load_agents_md()
        user_prefs = self._build_user_preferences_section()

        base = self._personality.build_system_prompt(
            agents_md_content=agents_md,
            user_preferences=user_prefs,
            session_roles=session_roles_summary,
            response_style=response_style,
            governance_principles=self._governance_principles,
        )

        parts: list[str] = [base]
        parts.append(f"## 現在日時\n{self._build_time_string()}")

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
