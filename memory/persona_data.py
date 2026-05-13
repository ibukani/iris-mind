from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path


_DEFAULT_PATH = "memory/persona_data.json"

_PERSONA_CATEGORIES = {
    "speech_style": "speech_styles",
    "personality_traits": "personality_traits",
}


class PersonaData:
    """ペルソナデータを専用JSONで管理。

    SemanticStore（Vector DB）を経由せず、軽量なJSONファイルで
    speech_style と personality_traits を蓄積・集計する。
    """

    def __init__(self, path: str = _DEFAULT_PATH):
        self.path = Path(path)
        self._data: dict = self._load()

    def _load(self) -> dict:
        if self.path.exists():
            try:
                return json.loads(self.path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, Exception):
                pass
        return {"speech_styles": [], "personality_traits": []}

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def add_entry(self, category: str, text: str, source: str = "reflection"):
        key = _PERSONA_CATEGORIES.get(category)
        if key is None:
            return
        now = datetime.now().isoformat(timespec="minutes")
        entries = self._data.setdefault(key, [])

        normalized = text.replace(" ", "").replace("　", "").replace("\n", "").replace("\r", "")
        for e in entries:
            en = e["text"].replace(" ", "").replace("　", "").replace("\n", "").replace("\r", "")
            if en == normalized:
                e["count"] = e.get("count", 1) + 1
                e["updated_at"] = now
                self._save()
                return

        entries.append({
            "text": text,
            "source": source,
            "count": 1,
            "timestamp": now,
            "updated_at": now,
        })
        self._save()

    def get_top(self, category: str, n: int = 3) -> list[dict]:
        key = _PERSONA_CATEGORIES.get(category)
        if key is None:
            return []
        entries = sorted(
            self._data.get(key, []),
            key=lambda e: e.get("count", 1),
            reverse=True,
        )
        return entries[:n]

    def get_all(self, category: str) -> list[dict]:
        key = _PERSONA_CATEGORIES.get(category)
        if key is None:
            return []
        return sorted(
            self._data.get(key, []),
            key=lambda e: e.get("count", 1),
            reverse=True,
        )

    def clear(self):
        self._data = {"speech_styles": [], "personality_traits": []}
        self._save()
