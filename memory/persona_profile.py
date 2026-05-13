from __future__ import annotations

from memory.persona_data import PersonaData


class PersonaProfile:
    """ペルソナ管理クラス。

    動的データ（speech_style / traits）は PersonaData（専用JSON）で管理。
    構造記憶（iris_profile.md）とは完全に分離されており、
    話し方・性格の動的データはシステムプロンプトに直接注入される。
    """

    def __init__(self, persona_data: PersonaData):
        self.persona_data = persona_data

    def get_speech_style(self) -> str:
        entries = self.persona_data.get_top("speech_style", 2)
        if not entries:
            return ""
        return "\n".join(f"- {e['text']}" for e in entries)

    def get_traits(self) -> str:
        entries = self.persona_data.get_top("personality_traits", 2)
        if not entries:
            return ""
        return "\n".join(f"- {e['text']}" for e in entries)

    def get_preferences_summary(self) -> str:
        return ""

    def get_all_speech_styles(self) -> list[dict]:
        return self.persona_data.get_all("speech_style")

    def get_all_traits(self) -> list[dict]:
        return self.persona_data.get_all("personality_traits")

    def update_from_reflection(self, reflection: dict):
        speech = reflection.get("speech_style", "").strip()
        traits = reflection.get("expressed_traits", "").strip()

        if speech:
            self.persona_data.add_entry("speech_style", speech)
        if traits:
            self.persona_data.add_entry("personality_traits", traits)

    def set_speech_style(self, text: str):
        self.persona_data.add_entry("speech_style", text, source="manual")

    def set_traits(self, text: str):
        self.persona_data.add_entry("personality_traits", text, source="manual")

    def reset(self):
        self.persona_data.clear()
