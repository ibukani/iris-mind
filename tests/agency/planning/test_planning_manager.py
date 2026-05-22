from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

from iris.agency.bus import InternalBus, PlanDecided
from iris.agency.execution.inhibition import GateVerdict, InhibitionController
from iris.agency.planning.decisions import ProactiveScoring
from iris.agency.planning.manager import PlanningManager
from iris.event.event_bus import EventBus
from iris.event.event_types import InputReady
from iris.kernel.config import Config, ProactiveConfig
from tests.conftest import FakeLLMProvider, FakePersonaData, FakePersonaProfile


def test_planning_manager_silent_proactive_interest_sampling() -> None:
    # Arrange
    internal_bus = MagicMock(spec=InternalBus)
    event_bus = EventBus()
    inhibition = MagicMock(spec=InhibitionController)
    inhibition.evaluate.return_value = GateVerdict(suppressed=False, score=0.8, reason="", go_signal=0.8)
    inhibition.is_topic_suppressed.return_value = False
    inhibition.consecutive_ignores = 0
    inhibition.last_proactive_time = 0.0
    inhibition.last_user_activity = 0.0
    inhibition.negative_mood_score = 0.0
    inhibition.outputs_since_input = 0
    inhibition.frequency_exceeded = False

    scoring = MagicMock(spec=ProactiveScoring)
    # total=0.6, drive=0.5, context=0.1 => is_silent_proactive=True
    scoring.compute.return_value = (0.6, {"drive": 0.5, "context": 0.1})

    config = Config()
    config.proactive = ProactiveConfig(speak_threshold=0.5)

    persona_data = FakePersonaData()
    persona_data.add_interest("宇宙の起源", 0.8)
    persona_profile = FakePersonaProfile(persona_data=persona_data)

    llm = FakeLLMProvider(
        responses=[{"message": {"content": "ビッグバン以前には何が存在したのか？", "role": "assistant"}}]
    )

    PlanningManager(
        internal_bus=internal_bus,
        event_bus=event_bus,
        inhibition=inhibition,
        scoring=scoring,
        config=config,
        memory=None,
        limbic=None,
        persona_profile=persona_profile,
        llm=llm,
    )

    # Act
    # InputReady を timer からの起動としてシミュレート
    event = InputReady(
        timestamp=datetime.now(),
        source="test",
        session_id="session_1",
        content="",
        context={"from_timer": True},
    )
    event_bus.publish(event)

    # Assert
    assert internal_bus.publish.call_count == 1
    call_args = internal_bus.publish.call_args[0][0]
    assert isinstance(call_args, PlanDecided)
    plan = call_args.plan
    assert plan["silent"] is True
    assert plan["tools_allowed"] is True
    assert plan["proactive_reason"] == "ビッグバン以前には何が存在したのか？"
    assert plan["interest_topic"] == "宇宙の起源"


def test_planning_manager_escalation_event() -> None:
    # Arrange
    internal_bus = MagicMock(spec=InternalBus)
    event_bus = EventBus()
    inhibition = MagicMock(spec=InhibitionController)
    inhibition.evaluate.return_value = GateVerdict(suppressed=False, score=0.8, reason="", go_signal=0.8)

    scoring = MagicMock(spec=ProactiveScoring)

    config = Config()
    config.proactive = ProactiveConfig()

    PlanningManager(
        internal_bus=internal_bus,
        event_bus=event_bus,
        inhibition=inhibition,
        scoring=scoring,
        config=config,
        memory=None,
        limbic=None,
        persona_profile=None,
        llm=None,
    )

    # Act
    # escalation イベントを発行
    event = InputReady(
        timestamp=datetime.now(),
        source="test",
        session_id="session_1",
        content="",
        context={"escalation": True, "topic": "宇宙の起源", "summary": "ビッグバンによる宇宙の膨張"},
    )
    event_bus.publish(event)

    # Assert
    assert internal_bus.publish.call_count == 1
    call_args = internal_bus.publish.call_args[0][0]
    assert isinstance(call_args, PlanDecided)
    plan = call_args.plan
    assert plan["silent"] is False
    assert plan["streaming"] is True
    assert "宇宙の起源" in plan["content"]
    assert "ビッグバンによる宇宙の膨張" in plan["content"]
    assert "システムからの内部指示" in plan["content"]
