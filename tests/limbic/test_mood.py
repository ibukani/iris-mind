from __future__ import annotations

import time

from iris.limbic.models import CompanionEmotion, PlutchikEmotion
from iris.limbic.mood import MoodDynamics


class TestMoodDynamics:
    def setup_method(self) -> None:
        self.mood = MoodDynamics()

    def test_initial_mood(self) -> None:
        result = self.mood.get_mood()
        assert result.valence == 0.0
        assert result.arousal == 0.0
        assert result.dominance == 0.0

    def test_update_mood(self) -> None:
        emotion = CompanionEmotion(
            primary=PlutchikEmotion.JOY,
            intensity=0.8,
            valence=0.8,
            arousal=0.6,
            dominance=0.6,
        )
        result = self.mood.update(emotion)
        assert result.valence > 0.0

    def test_mood_decay(self) -> None:
        emotion = CompanionEmotion(
            primary=PlutchikEmotion.JOY,
            intensity=0.8,
            valence=0.8,
            arousal=0.6,
            dominance=0.6,
        )
        self.mood.update(emotion)
        time.sleep(0.1)
        result = self.mood.get_mood()
        assert result.valence < 0.8

    def test_mood_bounds(self) -> None:
        emotion = CompanionEmotion(
            primary=PlutchikEmotion.JOY,
            intensity=1.0,
            valence=1.0,
            arousal=1.0,
            dominance=1.0,
        )
        result = self.mood.update(emotion)
        assert -1.0 <= result.valence <= 1.0
        assert -1.0 <= result.arousal <= 1.0
        assert -1.0 <= result.dominance <= 1.0

    def test_get_state(self) -> None:
        state = self.mood.get_state()
        assert "valence" in state
        assert "arousal" in state
        assert "dominance" in state
