from __future__ import annotations

import time

import pytest

from iris.agency.inhibition.gate import _Gate
from iris.agency.inhibition.handler import _InhibitionEventHandler
from iris.agency.inhibition.manager import InhibitionManager
from iris.agency.inhibition.models import (
    BUILTIN_SUPPRESSION_PROFILES,
    Pathway,
    SuppressionProfile,
)
from iris.agency.inhibition.striatum import _Striatum
from iris.agency.planning.models import Plan, PlanReason
from iris.event.event_bus import EventBus
from iris.io.events import InhibitionRequestEvent
from iris.kernel.config import InhibitionConfig

pytestmark = pytest.mark.legacy


def _make_plan(reason: PlanReason = PlanReason.USER_INPUT, room_id: str = "") -> Plan:
    return Plan(content="test", reason=reason, room_id=room_id)


class TestSuppressionProfile:
    def test_frozen(self) -> None:
        profile = SuppressionProfile(blocked_reasons=frozenset({"a"}), priority=5)
        assert profile.blocked_reasons == frozenset({"a"})
        assert profile.priority == 5

    def test_builtin_profiles_exist(self) -> None:
        assert "speaking" in BUILTIN_SUPPRESSION_PROFILES
        assert "voice_recording" in BUILTIN_SUPPRESSION_PROFILES
        assert "hyperdirect" in BUILTIN_SUPPRESSION_PROFILES

    def test_hyperdirect_blocks_all(self) -> None:
        profile = BUILTIN_SUPPRESSION_PROFILES["hyperdirect"]
        for reason in PlanReason:
            assert reason.value in profile.blocked_reasons

    def test_speaking_blocks_only_proactive(self) -> None:
        profile = BUILTIN_SUPPRESSION_PROFILES["speaking"]
        assert PlanReason.USER_INPUT.value not in profile.blocked_reasons
        assert PlanReason.PROACTIVE_CURIOSITY.value in profile.blocked_reasons
        assert PlanReason.PROACTIVE_ESCALATION.value in profile.blocked_reasons
        assert PlanReason.TIMER_EVENT.value in profile.blocked_reasons


class TestStriatum:
    def _make_striatum(self) -> _Striatum:
        config = InhibitionConfig()
        gate = _Gate(config)
        return _Striatum(gate, config)

    def test_suppress_and_unsuppress(self) -> None:
        s = self._make_striatum()
        assert not s.is_suppressed("voice_recording")
        s.suppress("voice_recording", duration=10.0)
        assert s.is_suppressed("voice_recording")
        s.unsuppress("voice_recording")
        assert not s.is_suppressed("voice_recording")

    def test_suppress_permanent(self) -> None:
        s = self._make_striatum()
        s.suppress("speaking")
        assert s.is_suppressed("speaking")

    def test_suppress_with_custom_profile(self) -> None:
        s = self._make_striatum()
        custom = SuppressionProfile(blocked_reasons=frozenset({PlanReason.USER_INPUT.value}), priority=99)
        s.suppress("custom_reason", profile=custom)
        assert s.is_suppressed("custom_reason")

    def test_evaluate_suppresses_matching_plan(self) -> None:
        s = self._make_striatum()
        s.suppress("speaking", duration=10.0)
        plan = _make_plan(PlanReason.PROACTIVE_CURIOSITY)
        decision = s.evaluate(plan)
        assert not decision.allow
        assert decision.pathway == Pathway.INDIRECT

    def test_evaluate_allows_non_matching_plan(self) -> None:
        s = self._make_striatum()
        s.suppress("speaking", duration=10.0)
        plan = _make_plan(PlanReason.USER_INPUT)
        decision = s.evaluate(plan)
        assert decision.allow

    def test_evaluate_hyperdirect_blocks_all(self) -> None:
        s = self._make_striatum()
        s.suppress("hyperdirect", duration=10.0)
        for reason in PlanReason:
            plan = _make_plan(reason)
            decision = s.evaluate(plan)
            assert not decision.allow
            assert decision.pathway == Pathway.HYPERDIRECT

    def test_evaluate_expired_suppression_allows(self) -> None:
        s = self._make_striatum()
        s.suppress("voice_recording", duration=0.01)
        time.sleep(0.02)
        plan = _make_plan(PlanReason.PROACTIVE_CURIOSITY)
        decision = s.evaluate(plan)
        assert decision.allow

    def test_evaluate_room_scoped_suppression(self) -> None:
        s = self._make_striatum()
        s.suppress("voice_recording", duration=10.0, room_id="room1")
        plan_other = _make_plan(PlanReason.PROACTIVE_CURIOSITY, room_id="room2")
        plan_same = _make_plan(PlanReason.PROACTIVE_CURIOSITY, room_id="room1")
        assert s.evaluate(plan_other).allow
        assert not s.evaluate(plan_same).allow

    def test_get_active_suppressions(self) -> None:
        s = self._make_striatum()
        s.suppress("speaking", duration=10.0)
        s.suppress("voice_recording")
        active = s.get_active_suppressions()
        reasons = {e["reason"] for e in active}
        assert "speaking" in reasons
        assert "voice_recording" in reasons

    def test_get_state(self) -> None:
        s = self._make_striatum()
        s.suppress("speaking", duration=5.0)
        state = s.get_state()
        assert "suppressions" in state
        assert any("speaking" in k for k in state["suppressions"])

    def test_custom_profile_blocks_user_input(self) -> None:
        s = self._make_striatum()
        custom = SuppressionProfile(blocked_reasons=frozenset({PlanReason.USER_INPUT.value}), priority=10)
        s.suppress("block_input", profile=custom)
        plan = _make_plan(PlanReason.USER_INPUT)
        decision = s.evaluate(plan)
        assert not decision.allow

    def test_has_active_suppression_with_permanent(self) -> None:
        s = self._make_striatum()
        assert not s.has_active_suppression
        s.suppress("speaking")
        assert s.has_active_suppression

    def test_has_active_suppression_with_timed(self) -> None:
        s = self._make_striatum()
        s.suppress("voice_recording", duration=10.0)
        assert s.has_active_suppression

    def test_has_active_suppression_none_when_expired(self) -> None:
        s = self._make_striatum()
        s.suppress("voice_recording", duration=0.01)
        time.sleep(0.02)
        assert not s.has_active_suppression

    def test_should_suppress_proactive_reason(self) -> None:
        s = self._make_striatum()
        s.suppress("speaking", duration=10.0)
        assert s.should_suppress(PlanReason.PROACTIVE_CURIOSITY.value)
        assert s.should_suppress(PlanReason.PROACTIVE_ESCALATION.value)
        assert s.should_suppress(PlanReason.TIMER_EVENT.value)
        assert not s.should_suppress(PlanReason.USER_INPUT.value)

    def test_should_suppress_room_scoped(self) -> None:
        s = self._make_striatum()
        s.suppress("speaking", duration=10.0, room_id="room1")
        assert s.should_suppress(PlanReason.PROACTIVE_CURIOSITY.value, room_id="room1")
        assert not s.should_suppress(PlanReason.PROACTIVE_CURIOSITY.value, room_id="room2")

    def test_should_suppress_custom_profile(self) -> None:
        s = self._make_striatum()
        custom = SuppressionProfile(blocked_reasons=frozenset({PlanReason.USER_INPUT.value}), priority=10)
        s.suppress("block_input", profile=custom)
        assert s.should_suppress(PlanReason.USER_INPUT.value)
        assert not s.should_suppress(PlanReason.PROACTIVE_CURIOSITY.value)


class TestInhibitionHandler:
    def _setup(self) -> tuple[EventBus, InhibitionManager]:
        bus = EventBus()
        config = InhibitionConfig()
        inhibition = InhibitionManager(config)
        _InhibitionEventHandler(event_bus=bus, inhibition=inhibition)
        return bus, inhibition

    def test_suppress_via_message_event(self) -> None:
        bus, inhibition = self._setup()
        bus.publish(
            InhibitionRequestEvent(
                timestamp=None,
                source="io",
                action="true",
                reason="voice_recording",
            )
        )
        assert inhibition.is_suppressed("voice_recording")

    def test_unsuppress_via_message_event(self) -> None:
        bus, inhibition = self._setup()
        bus.publish(
            InhibitionRequestEvent(
                timestamp=None,
                source="io",
                action="true",
                reason="voice_recording",
            )
        )
        assert inhibition.is_suppressed("voice_recording")
        bus.publish(
            InhibitionRequestEvent(
                timestamp=None,
                source="io",
                action="false",
                reason="voice_recording",
            )
        )
        assert not inhibition.is_suppressed("voice_recording")

    def test_suppress_with_duration(self) -> None:
        bus, inhibition = self._setup()
        bus.publish(
            InhibitionRequestEvent(
                timestamp=None,
                source="io",
                action="true",
                reason="speaking",
                duration=0.01,
            )
        )
        assert inhibition.is_suppressed("speaking")
        time.sleep(0.02)
        assert not inhibition.is_suppressed("speaking")

    def test_ignores_non_inhibition_action(self) -> None:
        bus, inhibition = self._setup()
        bus.publish(
            InhibitionRequestEvent(
                timestamp=None,
                source="io",
                action="bogus",
                reason="voice_recording",
            )
        )
        assert not inhibition.is_suppressed("voice_recording")

    def test_invalid_action_ignored(self) -> None:
        bus, inhibition = self._setup()
        # action が未知の値の場合は suppress しない
        bus.publish(
            InhibitionRequestEvent(
                timestamp=None,
                source="io",
                action="invalid",
                reason="voice_recording",
            )
        )
        assert not inhibition.is_suppressed("voice_recording")

    def test_negative_duration_treated_as_permanent(self) -> None:
        bus, inhibition = self._setup()
        # duration=0 は永続
        bus.publish(
            InhibitionRequestEvent(
                timestamp=None,
                source="io",
                action="true",
                reason="speaking",
                duration=0.0,
            )
        )
        assert inhibition.is_suppressed("speaking")

    def test_room_scoped_suppress(self) -> None:
        bus, inhibition = self._setup()
        bus.publish(
            InhibitionRequestEvent(
                timestamp=None,
                source="io",
                action="true",
                reason="voice_recording",
                room_id="room1",
            )
        )
        assert inhibition.is_suppressed("voice_recording", room_id="room1")
        assert not inhibition.is_suppressed("voice_recording", room_id="room2")
