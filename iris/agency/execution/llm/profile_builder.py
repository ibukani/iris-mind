from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, Any

from langchain_core.messages import SystemMessage

if TYPE_CHECKING:
    from iris.agency.modulation import ModulationState
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
        current_display_name: str = "",
        room_id: str = "",
        account_id: str = "",
        active_users: list[tuple[str, str]] | None = None,
        modulation: ModulationState | None = None,
    ) -> SystemMessage:
        agents_md = self._load_agents_md()
        user_prefs = self._build_user_preferences_section(room_id=room_id, account_id=account_id)
        affective_guidance = "\n".join(modulation.prompt_lines) if modulation else ""

        base = self._personality.build_system_prompt(
            agents_md_content=agents_md,
            user_preferences=user_prefs,
            response_style=response_style,
            governance_principles=self._governance_principles,
            affective_guidance=affective_guidance,
        )

        parts: list[str] = [base]
        parts.append(f"## 現在日時\n{self._build_time_string()}")

        participants = self._build_participants_section(
            room_id=room_id,
            current_display_name=current_display_name,
            active_users=active_users,
        )
        if participants:
            parts.append(participants)

        return SystemMessage(content="\n\n".join(parts))

    def _load_agents_md(self) -> str:
        return self._agents_md_store.load() if self._agents_md_store else ""

    def _build_user_preferences_section(self, room_id: str = "", account_id: str = "") -> str:
        prefs_list = self._memory.get_user_preferences(room_id=room_id, account_id=account_id) if self._memory else []
        seen: set[str] = set()
        unique_prefs: list[str] = []
        for p in prefs_list:
            c = p.get("content", "").strip()
            if c and c not in seen:
                seen.add(c)
                unique_prefs.append(f"- {c}")
        return "\n".join(unique_prefs)

    def _build_participants_section(
        self,
        room_id: str = "",
        current_display_name: str = "",
        active_users: list[tuple[str, str]] | None = None,
    ) -> str:
        users = active_users or []
        if not users and self._memory and room_id:
            users = self._memory.short_term.get_users_by_room(room_id)

        if not users:
            if current_display_name:
                return f"## 現在の会話相手\n{current_display_name}"
            return ""

        if len(users) == 1:
            _, nick = users[0]
            return f"## 現在の会話相手\n{nick}"

        names = [nick for _, nick in users]
        return "## ルームの参加者\n" + "\n".join(f"- {n}" for n in names)

    @staticmethod
    def _build_time_string() -> str:
        dt_now = datetime.datetime.now()
        weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        return f"{dt_now.strftime('%Y-%m-%d %H:%M:%S')} ({weekdays[dt_now.weekday()]})"
