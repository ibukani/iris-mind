from __future__ import annotations
import json
import re
from datetime import datetime
from pathlib import Path

from memory.stores import AgentsMdStore

_STATIC_SECTIONS = ["Known Structure", "My Capabilities", "My Rules"]
_DYNAMIC_SECTIONS = ["My Speech Style", "My Personality Traits"]
_SECTION_TAG_RE = re.compile(r"^## (.+)$", re.MULTILINE)

_DEFAULT_JSON = {
    "version": "1.0",
    "speech_style": [],
    "personality_traits": [],
    "created_at": "",
    "updated_at": "",
}


class PersonaProfile:
    """ペルソナ管理クラス。

    - 動的データ（speech_style / traits）は memory/persona_data.json（構造化JSON）で管理
    - iris_profile.md は起動時/明示的指示時にビューとして再生成
    - 静的部分（Known Structure等）は iris_profile.md からテンプレートとして抽出
    - SemanticStore操作は行わない（呼び出し元の _run_reflexion_and_save が担当）
    """

    def __init__(self, store: AgentsMdStore, json_path: str = "memory/persona_data.json"):
        self.store = store
        self.json_path = Path(json_path)
        self._template: dict[str, str] = {}
        self._data: dict = {}
        self._load_template()
        self._load_json()
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
    # JSON管理（動的データの永続化）
    # ============================================================

    def _load_json(self):
        if self.json_path.exists():
            try:
                self._data = json.loads(self.json_path.read_text(encoding="utf-8"))
                return
            except (json.JSONDecodeError, OSError):
                pass
        self._data = dict(_DEFAULT_JSON)

    def _save_json(self):
        self._data["updated_at"] = datetime.now().isoformat(timespec="minutes")
        self.json_path.parent.mkdir(parents=True, exist_ok=True)
        self.json_path.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # ============================================================
    # マイグレーション（iris_profile.md の旧動的セクション → JSON）
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
            self._save_json()
            self.regenerate_view()

    # ============================================================
    # ビュー再生成（JSON → iris_profile.md）
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

        md = "\n".join(parts).strip()
        self.store.update(md)

    # ============================================================
    # エントリ操作
    # ============================================================

    def _add_entry(self, category: str, text: str, source: str = "reflection"):
        now = datetime.now().isoformat(timespec="minutes")
        entries = self._data.setdefault(category, [])
        norm = text.replace(" ", "").replace("　", "")

        for e in entries:
            existing_norm = e.get("text", "").replace(" ", "").replace("　", "")
            if existing_norm == norm:
                e["count"] = e.get("count", 1) + 1
                e["updated_at"] = now
                return

        entries.append({
            "text": text,
            "source": source,
            "timestamp": now,
            "count": 1,
        })

    def _get_top_entries(self, category: str, n: int = 3) -> list[dict]:
        entries = self._data.get(category, [])
        return sorted(entries, key=lambda e: e.get("count", 1), reverse=True)[:n]

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
        return list(self._data.get("speech_style", []))

    def get_all_traits(self) -> list[dict]:
        return list(self._data.get("personality_traits", []))

    def update_from_reflection(self, reflection: dict):
        speech = reflection.get("speech_style", "").strip()
        traits = reflection.get("expressed_traits", "").strip()

        if speech:
            self._add_entry("speech_style", speech)
        if traits:
            self._add_entry("personality_traits", traits)

        if speech or traits:
            self._save_json()

    def set_speech_style(self, text: str):
        self._data["speech_style"] = [{"text": text, "source": "manual",
                                        "timestamp": datetime.now().isoformat(timespec="minutes"),
                                        "count": 99}]
        self._save_json()
        self.regenerate_view()

    def set_traits(self, text: str):
        self._data["personality_traits"] = [{"text": text, "source": "manual",
                                              "timestamp": datetime.now().isoformat(timespec="minutes"),
                                              "count": 99}]
        self._save_json()
        self.regenerate_view()

    def reset(self):
        self._data = dict(_DEFAULT_JSON)
        self._save_json()
        self.regenerate_view()
