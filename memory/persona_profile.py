from __future__ import annotations
import re

from memory.stores import AgentsMdStore
from memory.persona_data import PersonaData

_STATIC_SECTIONS = ["Known Structure", "My Capabilities", "My Rules"]
_DYNAMIC_SECTIONS = ["My Speech Style", "My Personality Traits"]
_SECTION_TAG_RE = re.compile(r"^## (.+)$", re.MULTILINE)


class PersonaProfile:
    """ペルソナ管理クラス。

    - 動的データ（speech_style / traits）は PersonaData（専用JSON）で管理
    - iris_profile.md は起動時/明示的指示時にビューとして再生成
    - 静的部分（Known Structure等）は iris_profile.md からテンプレートとして抽出
    """

    def __init__(self, store: AgentsMdStore, persona_data: PersonaData | None = None):
        self.store = store
        self.persona_data = persona_data or PersonaData()
        self._template: dict[str, str] = {}
        self._load_template()
        self._migrate_if_needed()

    # ============================================================
    # テンプレート管理（静的部分の抽出・保持）
    # ============================================================

    def _load_template(self):
        raw = self.store.load()
        if not raw:
            self._template = {}
            return
        sections = self._parse_sections(raw)
        self._template = {k: v for k, v in sections.items()
                          if k in _STATIC_SECTIONS or k == "__header__"}

    @staticmethod
    def _parse_sections(md: str) -> dict[str, str]:
        sections: dict[str, str] = {}
        current_name = "__header__"
        current_lines: list[str] = []
        for line in md.split("\n"):
            m = _SECTION_TAG_RE.match(line)
            if m:
                sections[current_name] = "\n".join(current_lines).strip()
                current_name = m.group(1)
                current_lines = []
            else:
                current_lines.append(line)
        if current_lines:
            sections[current_name] = "\n".join(current_lines).strip()
        return sections

    # ============================================================
    # マイグレーション（SemanticStore 時代のデータを PersonaData に移行）
    # ============================================================

    def _migrate_if_needed(self):
        raw = self.store.load()
        sections = self._parse_sections(raw)
        migrated = False

        section_map = {"My Speech Style": "speech_style",
                       "My Personality Traits": "personality_traits"}
        for section_name, json_key in section_map.items():
            if section_name not in sections:
                continue
            text = sections[section_name].strip()
            text = re.sub(r"^- ", "", text, flags=re.MULTILINE).strip()
            if text and "まだ確立" not in text:
                existing = self.persona_data.get_all(json_key)
                if not existing:
                    self.persona_data.add_entry(json_key, text, source="migration")
                    migrated = True

        if migrated:
            self.regenerate_view()

    # ============================================================
    # ビュー再生成（PersonaData → iris_profile.md）
    # ============================================================

    def regenerate_view(self):
        header = self._template.get("__header__", "# Iris プロフィール（自己認識用）")
        header = header.split("##")[0].strip()
        parts = [header, ""]

        section_map = {"My Speech Style": "speech_style",
                       "My Personality Traits": "personality_traits"}
        for section_name, json_key in section_map.items():
            entries = self.persona_data.get_top(json_key, 3)
            if entries:
                parts.append(f"## {section_name}")
                parts.extend(f"- {e['text']}" for e in entries)
                parts.append("")

        for name in _STATIC_SECTIONS:
            content = self._template.get(name, "").strip()
            if content:
                parts.append(f"## {name}")
                parts.append(content)
                parts.append("")

        md = "\n".join(parts).strip() + "\n"
        self.store.update(md)

    # ============================================================
    # パブリックAPI
    # ============================================================

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

        self.regenerate_view()

    def set_speech_style(self, text: str):
        self.persona_data.add_entry("speech_style", text, source="manual")
        self.regenerate_view()

    def set_traits(self, text: str):
        self.persona_data.add_entry("personality_traits", text, source="manual")
        self.regenerate_view()

    def reset(self):
        self.persona_data.clear()
        self.regenerate_view()
