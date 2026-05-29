from __future__ import annotations

from iris.limbic.generator import EmotionGenerator
from iris.limbic.models import AppraisalDimensions, CompanionEmotion, Mood, PlutchikEmotion


class TestEmotionGenerator:
    def setup_method(self) -> None:
        self.generator = EmotionGenerator()

    def test_generate_joy(self) -> None:
        appraisal = AppraisalDimensions(
            unpleasantness=0.0, control=0.8, responsibility=0.5, certainty=0.7, effort=0.2, attention=0.5
        )
        result = self.generator.generate(appraisal)
        assert isinstance(result, CompanionEmotion)
        assert result.primary in (PlutchikEmotion.JOY, PlutchikEmotion.TRUST)
        assert 0.0 <= result.intensity <= 1.0
        assert result.valence > 0

    def test_generate_anger(self) -> None:
        appraisal = AppraisalDimensions(
            unpleasantness=0.8, control=0.7, responsibility=0.8, certainty=0.5, effort=0.3, attention=0.5
        )
        result = self.generator.generate(appraisal)
        assert isinstance(result, CompanionEmotion)
        assert result.primary == PlutchikEmotion.ANGER

    def test_generate_with_mood(self) -> None:
        appraisal = AppraisalDimensions(
            unpleasantness=0.0, control=0.5, responsibility=0.5, certainty=0.5, effort=0.3, attention=0.5
        )
        mood = Mood(valence=0.5, arousal=0.3, dominance=0.4)
        result = self.generator.generate(appraisal, mood)
        assert isinstance(result, CompanionEmotion)
        assert result.valence != 0.0

    def test_generate_neutral(self) -> None:
        appraisal = AppraisalDimensions(
            unpleasantness=0.0, control=0.0, responsibility=0.0, certainty=0.0, effort=0.0, attention=0.0
        )
        result = self.generator.generate(appraisal)
        assert isinstance(result, CompanionEmotion)
        assert result.intensity >= 0.0

    def test_vad_bounds(self) -> None:
        appraisal = AppraisalDimensions(
            unpleasantness=1.0, control=1.0, responsibility=1.0, certainty=1.0, effort=1.0, attention=1.0
        )
        result = self.generator.generate(appraisal)
        assert -1.0 <= result.valence <= 1.0
        assert -1.0 <= result.arousal <= 1.0
        assert -1.0 <= result.dominance <= 1.0
