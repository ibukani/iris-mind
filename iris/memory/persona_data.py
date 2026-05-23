from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from loguru import logger

if TYPE_CHECKING:
    from iris.limbic.state import PsychometricState

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


def _resolve_category(category: str) -> str | None:
    category = _LEGACY_FIELD_MAP.get(category, category)
    return _PERSONA_CATEGORIES.get(category)


def _normalize(text: str) -> str:
    return text.replace(" ", "").replace("\u3000", "").replace("\n", "").replace("\r", "")


class PersonaData:
    """ペルソナの動的状態データを管理。

    PsychometricState のリスト（speech_quirks / state_traits / interests）を
    直接操作する。データの実体は PsychometricState に一元化されている。
    set_state() 未設定時は内蔵リストで動作する（テスト/単独利用）。
    """

    def __init__(self) -> None:
        self._state: PsychometricState | None = None
        self._fallback: dict[str, list[dict[str, Any]]] = {
            "speech_quirks": [],
            "state_traits": [],
            "interests": [],
        }

    def set_state(self, state: PsychometricState) -> None:
        self._state = state

    # ── 内部ヘルパ ──

    def _entries(self, key: str) -> list[dict[str, Any]]:
        if self._state is not None:
            return getattr(self._state, key, [])
        return self._fallback.get(key, [])

    def _set_entries(self, key: str, entries: list[dict[str, Any]]) -> None:
        if self._state is not None:
            setattr(self._state, key, entries)
        else:
            self._fallback[key] = entries

    def _mark_dirty(self) -> None:
        if self._state is not None:
            self._state.mark_dirty()

    # ── 話し方・性格傾向 ──

    def add_entry(self, category: str, text: str, source: str = "reflection") -> None:
        key = _resolve_category(category)
        if key is None:
            return
        now = datetime.now().isoformat(timespec="minutes")
        entries = self._entries(key)

        normalized = _normalize(text)
        for e in entries:
            if _normalize(e["text"]) == normalized:
                e["count"] = e.get("count", 1) + 1
                e["updated_at"] = now
                self._mark_dirty()
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
        self._set_entries(key, entries[:_MAX_ENTRIES])
        self._mark_dirty()
        logger.info("PersonaData: added {} entry ({} total)", category, len(self._entries(key)))

    def get_top(self, category: str, n: int = 3) -> list[dict]:
        key = _resolve_category(category)
        if key is None:
            return []
        entries = self._entries(key)
        entries = sorted(entries, key=lambda e: e.get("count", 1), reverse=True)
        return entries[:n]

    def get_all(self, category: str) -> list[dict]:
        key = _resolve_category(category)
        if key is None:
            return []
        entries = self._entries(key)
        return sorted(entries, key=lambda e: e.get("count", 1), reverse=True)

    def clear(self) -> None:
        for key in ("speech_quirks", "state_traits", "interests"):
            self._set_entries(key, [])
        self._mark_dirty()

    # ── 興味 ──

    def add_interest(self, topic: str, weight_delta: float) -> None:
        now = datetime.now().isoformat(timespec="minutes")
        interests = self._entries("interests")
        normalized_topic = topic.strip()

        for item in interests:
            if item["topic"].lower() == normalized_topic.lower():
                item["weight"] = max(0.0, min(1.0, item["weight"] + weight_delta))
                item["updated_at"] = now
                self._mark_dirty()
                return

        interests.append({"topic": normalized_topic, "weight": max(0.0, min(1.0, weight_delta)), "updated_at": now})
        interests.sort(key=lambda x: x["weight"], reverse=True)
        self._set_entries("interests", interests[:10])
        self._mark_dirty()

    def decay_interests(self, decay_rate: float = 0.05) -> None:
        interests = self._entries("interests")
        if not interests:
            return

        remaining = []
        for item in interests:
            new_weight = item["weight"] - decay_rate
            if new_weight > 0.1:
                item["weight"] = round(new_weight, 3)
                remaining.append(item)

        self._set_entries("interests", remaining)
        self._mark_dirty()

    def get_interests(self) -> list[dict]:
        return self._entries("interests")
