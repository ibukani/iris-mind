from __future__ import annotations

from typing import Any, TypedDict

from .models import EmotionResult


class EmotionPromptData(TypedDict, total=False):
    """LLM プロンプト埋め込み用の感情情報。"""

    emotion: str
    emotion_intensity: float
    valence: float
    arousal: float
    dominance: float
    mood_valence: float
    mood_arousal: float
    relationship_level: str
    trust: float
    familiarity: float


class EmotionSnapshot(TypedDict):
    emotion: dict[str, Any]
    mood: dict[str, Any]
    relationship: dict[str, Any]


class EmotionFullState(TypedDict, total=False):
    emotion: dict[str, Any] | None
    mood: dict[str, Any] | None
    relationship: dict[str, Any] | None
    history_count: int


class EmotionStateManager:
    """Limbic system の統合状態管理"""

    def __init__(self) -> None:
        self._latest: EmotionResult | None = None
        self._history: list[EmotionSnapshot] = []
        self._max_history = 50

    def update(self, result: EmotionResult) -> None:
        self._latest = result
        self._history.append(
            {
                "emotion": result.emotion.to_dict(),
                "mood": result.mood.to_dict(),
                "relationship": result.relationship.to_dict(),
            },
        )
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history :]

    def get_latest(self) -> EmotionResult | None:
        return self._latest

    def get_emotion_for_prompt(self) -> EmotionPromptData:
        """LLM プロンプトに組み込む感情情報を返す"""
        if self._latest is None:
            return EmotionPromptData()
        emotion = self._latest.emotion
        mood = self._latest.mood
        relationship = self._latest.relationship
        return EmotionPromptData(
            emotion=emotion.primary.value,
            emotion_intensity=emotion.intensity,
            valence=emotion.valence,
            arousal=emotion.arousal,
            dominance=emotion.dominance,
            mood_valence=mood.valence,
            mood_arousal=mood.arousal,
            relationship_level=relationship.level.name,
            trust=relationship.trust,
            familiarity=relationship.familiarity,
        )

    def get_state(self) -> EmotionFullState:
        if self._latest is None:
            return EmotionFullState(emotion=None, mood=None, relationship=None)
        return EmotionFullState(
            emotion=self._latest.emotion.to_dict(),
            mood=self._latest.mood.to_dict(),
            relationship=self._latest.relationship.to_dict(),
            history_count=len(self._history),
        )
