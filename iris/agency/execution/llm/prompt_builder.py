from __future__ import annotations

from dataclasses import dataclass
import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from iris.limbic.manager import LimbicManager
    from iris.llm.prompt import Personality
    from iris.memory.long_term.stores import AgentsMdStore
    from iris.memory.manager import MemoryManager
    from iris.memory.persona_profile import PersonaProfile


_SITUATION_INSTRUCTIONS: dict[str, str] = {
    "proactive": (
        "## 状況: 自発的な一声\n"
        "時間帯や会話の流れに合わせて、自然に声をかけてください。\n"
        "誰かと会話しているのではなく、自ら会話を始める場面です。"
    ),
}


@dataclass
class _PersonalityContext:
    agents_md: str
    current_state: str
    speech_style: str
    personality_traits: str
    user_prefs: str


class SystemPromptBuilder:
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
        context_hint: str = "",
        response_style: str = "",
        session_roles_summary: str = "",
    ) -> str:
        pctx = self._load_personality_context()

        prompt = self._personality.build_system_prompt(
            agents_md_content=pctx.agents_md,
            user_preferences=pctx.user_prefs,
            session_roles=session_roles_summary,
            response_style=response_style,
            speech_style=pctx.speech_style,
            personality_traits=pctx.personality_traits,
            governance_principles=self._governance_principles,
        )

        prompt += f"\n\n## 現在日時\n{self._build_time_string()}"

        if self._limbic:
            mood_desc = self._limbic.describe_mood()
            if mood_desc:
                prompt += f"\n\n## 現在の気分\n{mood_desc}"

        if pctx.current_state and "{speech_style}" not in self._personality.system_prompt_template:
            prompt += f"\n\n{pctx.current_state}"

        if context_hint:
            prompt += f"\n\n## 会話コンテキスト\n{context_hint}"

        return prompt

    def build_full(
        self,
        context_hint: str,
        response_style: str,
        situation: str,
        session_roles_summary: str = "",
    ) -> str:
        prompt = self.build(
            context_hint=context_hint,
            response_style=response_style,
            session_roles_summary=session_roles_summary,
        )
        if situation in _SITUATION_INSTRUCTIONS:
            prompt += "\n\n" + _SITUATION_INSTRUCTIONS[situation]
        return prompt

    def _load_personality_context(self) -> _PersonalityContext:
        agents_md = self._agents_md_store.load() if self._agents_md_store else ""
        current_state = self._persona_profile.get_current_state_section() if self._persona_profile else ""
        speech_style = self._persona_profile.get_speech_style() if self._persona_profile else ""
        personality_traits = self._persona_profile.get_traits() if self._persona_profile else ""
        user_prefs = self._build_user_preferences_section()
        return _PersonalityContext(
            agents_md=agents_md,
            current_state=current_state,
            speech_style=speech_style,
            personality_traits=personality_traits,
            user_prefs=user_prefs,
        )

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
