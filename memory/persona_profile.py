from __future__ import annotations
import re
from datetime import datetime

from memory.stores import AgentsMdStore, SemanticStore

_STATIC_SECTIONS = ["Known Structure", "My Capabilities", "My Rules"]
_DYNAMIC_SECTIONS = ["My Speech Style", "My Personality Traits"]
_SECTION_TAG_RE = re.compile(r"^## (.+)$", re.MULTILINE)


class PersonaProfile:
    """ペルソナ管理クラス。

    - 動的データ（speech_style / traits）は SemanticStore（ChromaDB + JSONL）で管理
    - iris_profile.md は起動時/明示的指示時にビューとして再生成
    - 静的部分（Known Structure等）は iris_profile.md からテンプレートとして抽出
    """

    def __init__(self, store: AgentsMdStore, semantic: SemanticStore | None = None):
        self.store = store
        self.semantic = semantic
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
    # SemanticStore からの集約
    # ============================================================

    def _aggregate_feedback(self, category: str) -> list[dict]:
        """SemanticStore からフィードバックを集約して件数順に返す。"""
        if not self.semantic:
            return []

        tag_map = {"speech_style": "speech_style", "personality_traits": "personality_trait"}
        tag = tag_map.get(category)
        if not tag:
            return []

        results = self.semantic.search(tag, max_results=50)
        text_counts: dict[str, dict] = {}
        for r in results:
            c = r.get("content", "")
            start = c.find("] ")
            if start == -1:
                continue
            text = c[start + 2:]
            m = re.search(r"\(source: (\w+),\s*count: (\d+)\)\s*$", text)
            if m:
                text = text[:m.start()].strip()
                source = m.group(1)
                count = int(m.group(2))
            else:
                source = "unknown"
                count = 1

            key = text.replace(" ", "").replace("　", "").replace("\n", "").replace("\r", "")
            if key in text_counts:
                text_counts[key]["count"] += count
                if text_counts[key].get("timestamp", "") < r.get("timestamp", ""):
                    text_counts[key]["updated_at"] = r.get("timestamp", "")
            else:
                text_counts[key] = {
                    "text": text,
                    "source": source,
                    "count": count,
                    "timestamp": r.get("timestamp", ""),
                    "updated_at": r.get("timestamp", ""),
                }

        return sorted(text_counts.values(), key=lambda e: e.get("count", 1), reverse=True)

    def _get_top_entries(self, category: str, n: int = 3) -> list[dict]:
        return self._aggregate_feedback(category)[:n]

    def _get_all_entries(self, category: str) -> list[dict]:
        return self._aggregate_feedback(category)

    # ============================================================
    # マイグレーション
    # ============================================================

    def _migrate_if_needed(self):
        raw = self.store.load()
        sections = self._parse_sections(raw)
        migrated = False

        for section_name, json_key in [("My Speech Style", "speech_style"),
                                        ("My Personality Traits", "personality_traits")]:
            if section_name not in sections:
                continue
            text = sections[section_name].strip()
            text = re.sub(r"^- ", "", text, flags=re.MULTILINE).strip()
            if text and "まだ確立" not in text:
                self._add_entry(json_key, text, source="migration")
                migrated = True

        if migrated:
            self.regenerate_view()

    # ============================================================
    # ビュー再生成（SemanticStore → iris_profile.md）
    # ============================================================

    def regenerate_view(self):
        header = self._template.get("__header__", "# Iris プロフィール（自己認識用）")
        header = header.split("##")[0].strip()
        parts = [header, ""]

        for section_name, json_key in [("My Speech Style", "speech_style"),
                                        ("My Personality Traits", "personality_traits")]:
            entries = self._get_top_entries(json_key, 3)
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
    # エントリ操作
    # ============================================================

    def _add_entry(self, category: str, text: str, source: str = "reflection"):
        now = datetime.now().isoformat(timespec="minutes")
        tag_map = {"speech_style": "speech_style", "personality_traits": "personality_trait"}
        tag = tag_map.get(category, category)

        if self.semantic:
            self.semantic.add({
                "type": "personality_feedback",
                "content": f"[{tag}] {text} (source: {source}, count: 1)",
                "tags": [tag, source],
                "timestamp": now,
            })

    # ============================================================
    # パブリックAPI
    # ============================================================

    def get_speech_style(self) -> str:
        entries = self._get_top_entries("speech_style", 2)
        if not entries:
            return ""
        return "\n".join(f"- {e['text']}" for e in entries)

    def get_traits(self) -> str:
        entries = self._get_top_entries("personality_traits", 2)
        if not entries:
            return ""
        return "\n".join(f"- {e['text']}" for e in entries)

    def get_preferences_summary(self) -> str:
        return ""

    def get_all_speech_styles(self) -> list[dict]:
        return self._get_all_entries("speech_style")

    def get_all_traits(self) -> list[dict]:
        return self._get_all_entries("personality_traits")

    def update_from_reflection(self, reflection: dict):
        speech = reflection.get("speech_style", "").strip()
        traits = reflection.get("expressed_traits", "").strip()

        if speech:
            self._add_entry("speech_style", speech)
        if traits:
            self._add_entry("personality_traits", traits)

        self.regenerate_view()

    def set_speech_style(self, text: str):
        self._add_entry("speech_style", text, source="manual")
        self.regenerate_view()

    def set_traits(self, text: str):
        self._add_entry("personality_traits", text, source="manual")
        self.regenerate_view()

    def reset(self):
        if self.semantic:
            self.semantic.clear()
        self.regenerate_view()