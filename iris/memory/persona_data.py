from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from iris.limbic.score import PsychometricState

_PERSONA_CATEGORIES = {
    "speech_quirks": "speech_quirks",
    "state_traits": "state_traits",
    "interests": "interests",
}

_LEGACY_FIELD_MAP = {
    "speech_styles": "speech_quirks",
    "personality_traits": "state_traits",
}

_MAX_ENTRIES = 5


class PersonaData:
    """ペルソナの現在状態データを管理。

    PsychometricState を永続化先とし、メモリ上の _data で更新を行う。
    """

    def __init__(self) -> None:
        self._state: PsychometricState | None = None
        self._data: dict[str, list] = {"speech_quirks": [], "state_traits": [], "interests": []}

    def set_state(self, state: PsychometricState) -> None:
        self._state = state
        self._data["speech_quirks"] = state.speech_quirks
        self._data["state_traits"] = state.state_traits
        self._data["interests"] = state.interests

    def _resolve_category(self, category: str) -> str | None:
        category = _LEGACY_FIELD_MAP.get(category, category)
        return _PERSONA_CATEGORIES.get(category)

    @staticmethod
    def _normalize(text: str) -> str:
        return text.replace(" ", "").replace("\u3000", "").replace("\n", "").replace("\r", "")

    def _save(self) -> None:
        if self._state is None:
            return
        self._state.speech_quirks = self._data.get("speech_quirks", [])
        self._state.state_traits = self._data.get("state_traits", [])
        self._state.interests = self._data.get("interests", [])
        self._state.mark_dirty()

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
        logger.info("PersonaData: added {} entry ({} total)", category, len(self._data[key]))

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
        interests = self._data.setdefault("interests", [])
        now = datetime.now().isoformat(timespec="minutes")
        normalized_topic = topic.strip()

        for item in interests:
            if item["topic"].lower() == normalized_topic.lower():
                item["weight"] = max(0.0, min(1.0, item["weight"] + weight_delta))
                item["updated_at"] = now
                self._save()
                return

        interests.append({"topic": normalized_topic, "weight": max(0.0, min(1.0, weight_delta)), "updated_at": now})
        interests.sort(key=lambda x: x["weight"], reverse=True)
        self._data["interests"] = interests[:10]
        self._save()

    def decay_interests(self, decay_rate: float = 0.05) -> None:
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
        return self._data.get("interests", [])
