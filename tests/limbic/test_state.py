from __future__ import annotations

from iris.limbic.models import EmotionResult
from iris.limbic.state import EmotionStateManager


class TestEmotionStateManager:
    def setup_method(self) -> None:
        self.state = EmotionStateManager()

    def test_initial_state(self) -> None:
        result = self.state.get_state()
        assert result["emotion"] is None
        assert result["mood"] is None

    def test_get_emotion_for_prompt_empty(self) -> None:
        result = self.state.get_emotion_for_prompt()
        assert result == {}

    def test_update_and_get(self) -> None:
        from iris.limbic.models import CompanionEmotion, Mood, PlutchikEmotion, RelationshipLevel, RelationshipState

        emotion = CompanionEmotion(
            primary=PlutchikEmotion.JOY,
            intensity=0.8,
            valence=0.8,
            arousal=0.6,
            dominance=0.6,
        )
        mood = Mood(valence=0.5, arousal=0.3, dominance=0.4)
        relationship = RelationshipState(level=RelationshipLevel.FAMILIAR)
        result = EmotionResult(
            appraisal=None,  # type: ignore
            emotion=emotion,
            mood=mood,
            relationship=relationship,
        )
        self.state.update(result)
        latest = self.state.get_latest()
        assert latest is not None
        assert latest.emotion.primary == PlutchikEmotion.JOY

    def test_get_emotion_for_prompt(self) -> None:
        from iris.limbic.models import CompanionEmotion, Mood, PlutchikEmotion, RelationshipLevel, RelationshipState

        emotion = CompanionEmotion(
            primary=PlutchikEmotion.JOY,
            intensity=0.8,
            valence=0.8,
            arousal=0.6,
            dominance=0.6,
        )
        mood = Mood(valence=0.5, arousal=0.3, dominance=0.4)
        relationship = RelationshipState(level=RelationshipLevel.FAMILIAR)
        result = EmotionResult(
            appraisal=None,  # type: ignore
            emotion=emotion,
            mood=mood,
            relationship=relationship,
        )
        self.state.update(result)
        prompt_data = self.state.get_emotion_for_prompt()
        assert prompt_data["emotion"] == "joy"
        assert prompt_data["emotion_intensity"] == 0.8
        assert prompt_data["relationship_level"] == "FAMILIAR"
