from __future__ import annotations

from iris.limbic.models import PlutchikEmotion
from iris.limbic.orchestrator import LimbicOrchestrator


class TestLimbicOrchestrator:
    def setup_method(self) -> None:
        self.orchestrator = LimbicOrchestrator()

    def test_process_joy(self) -> None:
        result = self.orchestrator.process("とても嬉しいです最高だ")
        assert result.emotion.valence > 0
        assert 0.0 <= result.emotion.intensity <= 1.0
        assert result.relationship.trust >= 0.1

    def test_process_anger(self) -> None:
        result = self.orchestrator.process("腹が立つ許せない最悪だ")
        assert result.emotion.valence < 0

    def test_process_neutral(self) -> None:
        result = self.orchestrator.process("今日は天気がいい")
        assert isinstance(result.emotion.primary, PlutchikEmotion)

    def test_process_updates_relationship(self) -> None:
        self.orchestrator.process("嬉しいです")
        profile = self.orchestrator.get_relationship_profile()
        assert profile["familiarity"] > 0.0

    def test_process_reappraisal(self) -> None:
        result = self.orchestrator.process("腹が立つ許せない最悪")
        if result.appraisal.unpleasantness > 0.7 and result.appraisal.control < 0.3:
            assert result.reappraisal_needed is True

    def test_get_state(self) -> None:
        self.orchestrator.process("嬉しいです")
        state = self.orchestrator.get_state()
        assert "emotion" in state
        assert "mood" in state
        assert "relationship" in state

    def test_get_emotion_for_prompt(self) -> None:
        self.orchestrator.process("嬉しいです")
        prompt_data = self.orchestrator.get_emotion_for_prompt()
        assert "emotion" in prompt_data
        assert "trust" in prompt_data


class TestLimbicOrchestratorPerAccount:
    def setup_method(self) -> None:
        self.orchestrator = LimbicOrchestrator()

    def test_process_with_account_id(self) -> None:
        result = self.orchestrator.process(
            "嬉しいです",
            account_id="user_a",
        )
        assert result.emotion.valence > 0
        profile = self.orchestrator.get_relationship_profile(account_id="user_a")
        assert profile["familiarity"] > 0.0

    def test_per_account_relationship_isolation(self) -> None:
        self.orchestrator.process("嬉しいです", account_id="user_a")
        self.orchestrator.process("腹が立つ許せない最悪", account_id="user_b")

        profile_a = self.orchestrator.get_relationship_profile(account_id="user_a")
        profile_b = self.orchestrator.get_relationship_profile(account_id="user_b")
        assert profile_a["trust_level"] > profile_b["trust_level"]

    def test_process_with_context(self) -> None:
        result = self.orchestrator.process(
            "今日は天気がいい",
            context={"room_id": "room_1", "is_direct_question": True},
            account_id="user_a",
        )
        assert isinstance(result.emotion.primary, PlutchikEmotion)
