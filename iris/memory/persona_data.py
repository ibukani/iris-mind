from __future__ import annotations

from datetime import datetime
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_PATH = ".iris/data/persona_data.json"

_PERSONA_CATEGORIES = {
    "speech_quirks": "speech_quirks",
    "state_traits": "state_traits",
}

# 後方互換: 旧フィールド名のマッピング
_LEGACY_FIELD_MAP = {
    "speech_styles": "speech_quirks",
    "personality_traits": "state_traits",
}

# カテゴリ別の最大保持エントリ数（上位N件 = 直近の状態のみ保持）
_MAX_ENTRIES = 5


class PersonaData:
    """ペルソナの現在状態データを専用JSONで管理。

    SemanticStore（Vector DB）を経由せず、軽量なJSONファイルで
    speech_quirks（話し方の現在状態）と state_traits（性格の現在状態）を管理する。
    各カテゴリは最大5件のみ保持し、累積肥大化を防ぐ。
    iris_profile.md（不変ベース）とは完全に分離。
    """

    def __init__(self, path: str = _DEFAULT_PATH) -> None:
        self.path = Path(path)
        self._data: dict[str, list] = self._load()

    def _load(self) -> dict[str, list]:
        if self.path.exists():
            try:
                raw: dict = json.loads(self.path.read_text(encoding="utf-8"))
                # 旧フィールド名を新フィールド名にマイグレート
                for old, new in _LEGACY_FIELD_MAP.items():
                    if old in raw and new not in raw:
                        raw[new] = raw.pop(old)
                return {
                    "speech_quirks": raw.get("speech_quirks", []),
                    "state_traits": raw.get("state_traits", []),
                }
            except (json.JSONDecodeError, Exception):
                pass
        return {"speech_quirks": [], "state_traits": []}

    def _resolve_category(self, category: str) -> str | None:
        category = _LEGACY_FIELD_MAP.get(category, category)
        return _PERSONA_CATEGORIES.get(category)

    @staticmethod
    def _normalize(text: str) -> str:
        return text.replace(" ", "").replace("\u3000", "").replace("\n", "").replace("\r", "")

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def add_entry(self, category: str, text: str, source: str = "reflection") -> None:
        key = self._resolve_category(category)
        if key is None:
            return
        now = datetime.now().isoformat(timespec="minutes")
        entries = self._data.setdefault(key, [])

        normalized = self._normalize(text)
        for e in entries:
            if self._normalize(e["text"]) == normalized:
                e["count"] = e.get("count", 1) + 1
                e["updated_at"] = now
                self._save()
                return

        entries.append(
            {
                "text": text,
                "source": source,
                "count": 1,
                "timestamp": now,
                "updated_at": now,
            }
        )
        entries.sort(key=lambda e: (e.get("count", 1), e.get("updated_at", "")), reverse=True)
        self._data[key] = entries[:_MAX_ENTRIES]
        self._save()
        logger.info("PersonaData: added %s entry (%d total)", category, len(self._data[key]))

    def get_top(self, category: str, n: int = 3) -> list[dict]:
        key = self._resolve_category(category)
        if key is None:
            return []
        entries = sorted(
            self._data.get(key, []),
            key=lambda e: e.get("count", 1),
            reverse=True,
        )
        return entries[:n]

    def get_all(self, category: str) -> list[dict]:
        key = self._resolve_category(category)
        if key is None:
            return []
        return sorted(
            self._data.get(key, []),
            key=lambda e: e.get("count", 1),
            reverse=True,
        )

    def clear(self) -> None:
        self._data = {"speech_quirks": [], "state_traits": []}
        self._save()
