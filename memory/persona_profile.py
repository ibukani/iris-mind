from __future__ import annotations
import re

from memory.stores import AgentsMdStore, SemanticStore


_SECTION_ORDER = [
    "My Speech Style",
    "My Personality Traits",
    "Known Structure",
    "My Capabilities",
    "My Rules",
]

_SECTION_TAG_RE = re.compile(r"^## (.+)$", re.MULTILINE)


class PersonaProfile:
    """ペルソナ管理クラス。
    AgentsMdStore (iris_profile.md, 2KB上限) にReflexion結果をマージし、
    動的に進化する自己認識を管理する。
    """

    def __init__(self, store: AgentsMdStore, semantic: SemanticStore):
        self.store = store
        self.semantic = semantic
        self._buf: dict[str, str] = {}  # section_name -> content lines (joined)
        self._sync_from_store()

    def _sync_from_store(self):
        raw = self.store.load()
        if not raw:
            self._buf = {}
            return
        self._buf = self._parse_sections(raw)

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

    def _build_md(self) -> str:
        header = self._buf.get("__header__", "# Iris プロフィール（自己認識用）")
        parts = [header, ""]
        for name in _SECTION_ORDER:
            content = self._buf.get(name, "").strip()
            if not content:
                continue
            parts.append(f"## {name}")
            parts.append(content)
            parts.append("")
        return "\n".join(parts).strip()

    def get_speech_style(self) -> str:
        return self._buf.get("My Speech Style", "")

    def get_traits(self) -> str:
        return self._buf.get("My Personality Traits", "")

    def get_preferences_summary(self) -> str:
        prefs = self.semantic.search("ユーザーの好み user preference", max_results=3)
        if not prefs:
            return ""
        lines = []
        for p in prefs:
            c = p.get("content", "").strip()
            if c:
                lines.append(f"- {c[:120]}")
        return "\n".join(lines) if lines else ""

    def update_from_reflection(self, reflection: dict):
        speech = reflection.get("speech_style", "").strip()
        traits = reflection.get("expressed_traits", "").strip()
        pref = reflection.get("preference", "").strip()
        lesson = reflection.get("lesson", "").strip()

        if speech:
            self._merge_into_section("My Speech Style", speech)
        if traits:
            self._merge_into_section("My Personality Traits", traits)

        if pref:
            self.semantic.add({
                "type": "preference",
                "content": pref,
                "tags": ["user_preference"],
                "timestamp": "",
                "context": "reflection",
            })
        if lesson:
            self.semantic.add({
                "type": "lesson",
                "content": lesson,
                "tags": [],
                "timestamp": "",
                "context": "reflection",
            })

        new_md = self._build_md()
        self.store.update(new_md)
        self._sync_from_store()

    def _merge_into_section(self, section: str, new_entry: str):
        existing = self._buf.get(section, "")

        if new_entry in existing:
            return

        entries = [e.strip() for e in existing.replace("- ", "").split("\n") if e.strip()]
        entries.append(new_entry)

        seen: set[str] = set()
        deduped: list[str] = []
        for e in entries:
            norm = e.replace(" ", "").replace("　", "")
            if norm not in seen:
                seen.add(norm)
                deduped.append(e)

        max_entries = 5
        if len(deduped) > max_entries:
            deduped = deduped[-max_entries:]

        self._buf[section] = "\n".join(f"- {e}" for e in deduped)

    def set_speech_style(self, text: str):
        self._buf["My Speech Style"] = text.strip()
        new_md = self._build_md()
        self.store.update(new_md)
        self._sync_from_store()

    def set_traits(self, text: str):
        self._buf["My Personality Traits"] = text.strip()
        new_md = self._build_md()
        self.store.update(new_md)
        self._sync_from_store()

    def reset(self):
        self._buf = {}
        md = "# Iris プロフィール（自己認識用）\n\nI am Iris, an autonomous AI assistant that learns and evolves."
        self.store.update(md)
        self._sync_from_store()
