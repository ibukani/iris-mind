from __future__ import annotations

import pytest

from iris.limbic.models import CompanionEmotion, PlutchikEmotion, RelationshipLevel
from iris.limbic.relationship import RelationshipManager

pytestmark = pytest.mark.legacy


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


class TestRelationshipManagerPerAccount:
    def setup_method(self) -> None:
        self.manager = RelationshipManager()

    def _joy(self) -> CompanionEmotion:
        return CompanionEmotion(
            primary=PlutchikEmotion.JOY,
            intensity=0.8,
            valence=0.8,
            arousal=0.6,
            dominance=0.6,
        )

    def test_per_account_isolation(self) -> None:
        self.manager.update(self._joy(), account_id="user_a")
        self.manager.update(self._joy(), account_id="user_b")

        state_a = self.manager.get_state(account_id="user_a")
        state_b = self.manager.get_state(account_id="user_b")
        assert state_a.trust == state_b.trust

        self.manager.update(
            CompanionEmotion(
                primary=PlutchikEmotion.ANGER,
                intensity=0.8,
                valence=-0.7,
                arousal=0.8,
                dominance=0.5,
            ),
            account_id="user_a",
        )
        state_a_after = self.manager.get_state(account_id="user_a")
        state_b_after = self.manager.get_state(account_id="user_b")
        assert state_a_after.trust < state_b_after.trust

    def test_per_account_profile(self) -> None:
        self.manager.update(self._joy(), account_id="user_a")
        profile = self.manager.get_profile(account_id="user_a")
        assert profile["trust_level"] > 0.1

        profile_default = self.manager.get_profile(account_id="nonexistent")
        assert profile_default["trust_level"] == 0.1

    def test_get_all_states(self) -> None:
        self.manager.update(self._joy(), account_id="user_a")
        self.manager.update(self._joy(), account_id="user_b")
        all_states = self.manager.get_all_states()
        assert "user_a" in all_states
        assert "user_b" in all_states

    def test_global_fallback(self) -> None:
        self.manager.update(self._joy())
        state = self.manager.get_state()
        assert state.trust > 0.1

    def test_per_account_level_upgrade(self) -> None:
        for _ in range(20):
            self.manager.update(self._joy(), account_id="user_a")
        state_a = self.manager.get_state(account_id="user_a")
        state_b = self.manager.get_state(account_id="user_b")
        assert state_a.level >= RelationshipLevel.FAMILIAR
        assert state_b.level == RelationshipLevel.ACQUAINTANCE


class TestRelationshipManagerApplyCandidateDelta:
    def setup_method(self) -> None:
        self.manager = RelationshipManager()

    def test_apply_trust_delta_increases(self) -> None:
        before = self.manager.get_state(account_id="acc1").trust
        new = self.manager.apply_candidate_delta(field="trust", delta=0.02, account_id="acc1")
        assert new.trust == before + 0.02
        # 状態はそのまま保存されている
        assert self.manager.get_state(account_id="acc1").trust == new.trust

    def test_apply_trust_delta_clamps_to_unit(self) -> None:
        # 1.0 を超える delta を与えても 1.0 で止まる
        new = self.manager.apply_candidate_delta(field="trust", delta=5.0, account_id="acc1")
        assert new.trust <= 1.0

    def test_apply_trust_delta_clamps_to_zero(self) -> None:
        new = self.manager.apply_candidate_delta(field="trust", delta=-5.0, account_id="acc1")
        assert new.trust >= 0.0

    def test_apply_familiarity_delta(self) -> None:
        before = self.manager.get_state().familiarity
        new = self.manager.apply_candidate_delta(field="familiarity", delta=0.05, account_id="acc1")
        assert new.familiarity == before + 0.05

    def test_apply_unknown_field_raises(self) -> None:
        import pytest

        with pytest.raises(ValueError, match="unsupported relationship field"):
            self.manager.apply_candidate_delta(field="invalid", delta=0.01, account_id="acc1")

    def test_apply_per_account_isolation(self) -> None:
        self.manager.apply_candidate_delta(field="trust", delta=0.05, account_id="acc1")
        state_b = self.manager.get_state(account_id="acc2")
        # acc1 の操作は acc2 に影響しない
        assert state_b.trust == 0.1
