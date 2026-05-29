from __future__ import annotations

from iris.limbic.appraiser import Appraiser
from iris.limbic.models import PrimaryAppraisal, SecondaryAppraisal


class TestAppraiser:
    def setup_method(self) -> None:
        self.appraiser = Appraiser()

    def test_appraise_primary_joy(self) -> None:
        result = self.appraiser.appraise_primary("とても嬉しいです")
        assert isinstance(result, PrimaryAppraisal)
        assert result.pleasantness > 0

    def test_appraise_primary_anger(self) -> None:
        result = self.appraiser.appraise_primary("腹が立つ")
        assert isinstance(result, PrimaryAppraisal)
        assert result.pleasantness < 0

    def test_appraise_primary_neutral(self) -> None:
        result = self.appraiser.appraise_primary("今日は天気がいい")
        assert isinstance(result, PrimaryAppraisal)
        assert -1.0 <= result.pleasantness <= 1.0

    def test_appraise_secondary(self) -> None:
        primary = PrimaryAppraisal(novelty=0.5, pleasantness=0.7, goal_relevance=0.8, agency=0.3, coping_potential=0.6)
        result = self.appraiser.appraise_secondary(primary, {"trust_level": 0.8, "familiarity": 0.5})
        assert isinstance(result, SecondaryAppraisal)
        assert result.accountability > 0
        assert result.control > 0

    def test_compute_dimensions(self) -> None:
        primary = PrimaryAppraisal(novelty=0.5, pleasantness=0.7, goal_relevance=0.8, agency=0.3, coping_potential=0.6)
        secondary = SecondaryAppraisal(accountability=0.5, control=0.6, controllability=0.7, social_norms=0.5)
        result = self.appraiser.compute_dimensions(primary, secondary)
        assert -1.0 <= result.unpleasantness <= 1.0
        assert -1.0 <= result.control <= 1.0
        assert -1.0 <= result.certainty <= 1.0

    def test_detect_word_emotions_multiple(self) -> None:
        result = self.appraiser.appraise_primary("嬉しいけど少し不安")
        assert isinstance(result, PrimaryAppraisal)

    def test_context_type_detection(self) -> None:
        result = self.appraiser.appraise_primary("助けてください相談です")
        assert isinstance(result, PrimaryAppraisal)
        assert result.goal_relevance > 0.5
