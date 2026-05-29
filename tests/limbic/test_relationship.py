from __future__ import annotations

from iris.limbic.models import CompanionEmotion, PlutchikEmotion, RelationshipLevel
from iris.limbic.relationship import RelationshipManager


class TestRelationshipManager:
    def setup_method(self) -> None:
        self.manager = RelationshipManager()

    def test_initial_state(self) -> None:
        state = self.manager.get_state()
        assert state.level == RelationshipLevel.ACQUAINTANCE
        assert state.trust == 0.1
        assert state.familiarity == 0.0

    def test_update_joy(self) -> None:
        emotion = CompanionEmotion(
            primary=PlutchikEmotion.JOY,
            intensity=0.8,
            valence=0.8,
            arousal=0.6,
            dominance=0.6,
        )
        result = self.manager.update(emotion)
        assert result.trust > 0.1
        assert result.familiarity > 0.0

    def test_update_anger_decreases_trust(self) -> None:
        emotion = CompanionEmotion(
            primary=PlutchikEmotion.ANGER,
            intensity=0.8,
            valence=-0.7,
            arousal=0.8,
            dominance=0.5,
        )
        result = self.manager.update(emotion)
        assert result.trust < 0.1

    def test_level_upgrade(self) -> None:
        emotion = CompanionEmotion(
            primary=PlutchikEmotion.TRUST,
            intensity=0.8,
            valence=0.5,
            arousal=0.2,
            dominance=0.3,
        )
        for _ in range(20):
            self.manager.update(emotion)
        state = self.manager.get_state()
        assert state.level >= RelationshipLevel.FAMILIAR

    def test_context_type_affects_disclosure(self) -> None:
        emotion = CompanionEmotion(
            primary=PlutchikEmotion.TRUST,
            intensity=0.5,
            valence=0.5,
            arousal=0.2,
            dominance=0.3,
        )
        self.manager.update(emotion, context_type="self_disclosure")
        state = self.manager.get_state()
        assert state.disclosure_depth > 0.0

    def test_get_profile(self) -> None:
        profile = self.manager.get_profile()
        assert "trust_level" in profile
        assert "familiarity" in profile
        assert "relationship_level" in profile
