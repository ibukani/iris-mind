from __future__ import annotations

from iris.memory.persona_data import PersonaData


class PersonaProfile:
    """ペルソナ管理クラス。

    動的データ（speech_quirks / state_traits）は PersonaData（専用JSON）で管理。
    構造記憶（iris_profile.md）とは完全に分離。iris_profile.md は config として不変。
    """

    def __init__(self, persona_data: PersonaData):
        self.persona_data = persona_data

    def get_speech_style(self) -> str:
        """上位1件の話し方の現在状態を返す（プロンプト上部セクション用）。"""
        entries = self.persona_data.get_top("speech_quirks", 1)
        if not entries:
            return ""
        return "\n".join(f"- {e['text']}" for e in entries)

    def get_traits(self) -> str:
        """上位1件の性格の現在状態を返す（プロンプト上部セクション用）。"""
        entries = self.persona_data.get_top("state_traits", 1)
        if not entries:
            return ""
        return "\n".join(f"- {e['text']}" for e in entries)

    def get_current_state_section(self) -> str:
        """現在の状態セクションを返す（空なら空文字）。

        iris_profile の基本性格・口調とは分離された「今この瞬間の傾向」。
        """
        traits = self.get_traits()
        styles = self.get_speech_style()
        parts = []
        if traits:
            parts.append(traits)
        if styles:
            parts.append(styles)
        if not parts:
            return ""
        return "## 現在の状態\n" + "\n".join(parts)

    def get_preferences_summary(self) -> str:
        return ""

    def get_all_speech_styles(self) -> list[dict]:
        return self.persona_data.get_all("speech_quirks")

    def get_all_traits(self) -> list[dict]:
        return self.persona_data.get_all("state_traits")

    def update_from_reflection(self, reflection: dict) -> None:
        """Reflexion結果からpersona_dataを差分更新する。"""
        speech = reflection.get("speech_style", "").strip()
        traits = reflection.get("expressed_traits", "").strip()
        if speech:
            self.persona_data.add_entry("speech_quirks", speech)
        if traits:
            self.persona_data.add_entry("state_traits", traits)

    def set_speech_style(self, text: str) -> None:
        self.persona_data.add_entry("speech_quirks", text, source="manual")

    def set_traits(self, text: str) -> None:
        self.persona_data.add_entry("state_traits", text, source="manual")

    def reset(self) -> None:
        self.persona_data.clear()
