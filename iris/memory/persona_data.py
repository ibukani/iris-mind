from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path

from loguru import logger

_DEFAULT_PATH = ".iris/data/persona_data.json"

_PERSONA_CATEGORIES = {
    "speech_quirks": "speech_quirks",
    "state_traits": "state_traits",
    "interests": "interests",
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
                    "interests": raw.get("interests", []),
                }
            except (json.JSONDecodeError, Exception):
                pass
        return {"speech_quirks": [], "state_traits": [], "interests": []}

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
        self._data = {"speech_quirks": [], "state_traits": [], "interests": []}
        self._save()

    def add_interest(self, topic: str, weight_delta: float) -> None:
        """興味トピックを追加または加重する。"""
        interests = self._data.setdefault("interests", [])
        now = datetime.now().isoformat(timespec="minutes")
        normalized_topic = topic.strip()

        for item in interests:
            if item["topic"].lower() == normalized_topic.lower():
                item["weight"] = max(0.0, min(1.0, item["weight"] + weight_delta))
                item["updated_at"] = now
                self._save()
                return

        # 新規追加
        interests.append({"topic": normalized_topic, "weight": max(0.0, min(1.0, weight_delta)), "updated_at": now})
        interests.sort(key=lambda x: x["weight"], reverse=True)
        # 上限数制限（上位10件まで）
        self._data["interests"] = interests[:10]
        self._save()

    def decay_interests(self, decay_rate: float = 0.05) -> None:
        """すべての興味の重みを自然減衰させ、閾値以下のものを削除する。"""
        interests = self._data.get("interests", [])
        if not interests:
            return

        remaining = []
        for item in interests:
            new_weight = item["weight"] - decay_rate
            if new_weight > 0.1:
                item["weight"] = round(new_weight, 3)
                remaining.append(item)

        self._data["interests"] = remaining
        self._save()

    def get_interests(self) -> list[dict]:
        """現在の興味リストを取得する。"""
        return self._data.get("interests", [])
