from __future__ import annotations

from typing import Any

from .models import EmotionResult


class EmotionStateManager:
    """Limbic system の統合状態管理"""

    def __init__(self) -> None:
        self._latest: EmotionResult | None = None
        self._history: list[dict[str, Any]] = []
        self._max_history = 50

    def update(self, result: EmotionResult) -> None:
        self._latest = result
        self._history.append(
            {
                "emotion": result.emotion.to_dict(),
                "mood": result.mood.to_dict(),
                "relationship": result.relationship.to_dict(),
            }
        )
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history :]

    def get_latest(self) -> EmotionResult | None:
        return self._latest

    def get_emotion_for_prompt(self) -> dict[str, Any]:
        """LLM プロンプトに組み込む感情情報を返す"""
        if self._latest is None:
            return {}
        emotion = self._latest.emotion
        mood = self._latest.mood
        relationship = self._latest.relationship
        return {
            "emotion": emotion.primary.value,
            "emotion_intensity": emotion.intensity,
            "valence": emotion.valence,
            "arousal": emotion.arousal,
            "dominance": emotion.dominance,
            "mood_valence": mood.valence,
            "mood_arousal": mood.arousal,
            "relationship_level": relationship.level.name,
            "trust": relationship.trust,
            "familiarity": relationship.familiarity,
        }

    def get_state(self) -> dict[str, Any]:
        if self._latest is None:
            return {"emotion": None, "mood": None, "relationship": None}
        return {
            "emotion": self._latest.emotion.to_dict(),
            "mood": self._latest.mood.to_dict(),
            "relationship": self._latest.relationship.to_dict(),
            "history_count": len(self._history),
        }
