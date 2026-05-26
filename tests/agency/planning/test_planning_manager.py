from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

from langchain_core.messages import AIMessage

from iris.agency import (
    InternalBus,
    PlanDecided,
    PlanningManager,
    ProactiveScorer,
)
from iris.event.event_bus import EventBus
from iris.event.event_types import InputReady
from iris.kernel.config import Config, ProactiveConfig


def test_planning_manager_silent_proactive_interest_sampling() -> None:
    internal_bus = MagicMock(spec=InternalBus)
    event_bus = EventBus()
    scoring = MagicMock(spec=ProactiveScorer)
    scoring.compute.return_value = (0.6, {"drive": 0.5, "context": 0.1})

    config = Config()
    config.proactive = ProactiveConfig(speak_threshold=0.5)

    llm = MagicMock()
    llm.chat = MagicMock(return_value=AIMessage(content="ビッグバン以前には何が存在したのか？"))

    PlanningManager(
        internal_bus=internal_bus,
        event_bus=event_bus,
        scoring=scoring,
        config=config,
        memory=None,
        llm=llm,
    )

    event = InputReady(
        timestamp=datetime.now(),
        source="test",
        session_id="session_1",
        content="",
        context={"from_timer": True},
    )
    event_bus.publish(event)

    assert internal_bus.publish.call_count == 1
    call_args = internal_bus.publish.call_args[0][0]
    assert isinstance(call_args, PlanDecided)
    plan = call_args.plan
    assert plan.silent is True


def test_planning_manager_escalation_event() -> None:
    internal_bus = MagicMock(spec=InternalBus)
    event_bus = EventBus()
    scoring = MagicMock(spec=ProactiveScorer)

    config = Config()
    config.proactive = ProactiveConfig()

    PlanningManager(
        internal_bus=internal_bus,
        event_bus=event_bus,
        scoring=scoring,
        config=config,
        memory=None,
        llm=None,
    )

    event = InputReady(
        timestamp=datetime.now(),
        source="test",
        session_id="session_1",
        content="",
        context={"escalation": True, "topic": "宇宙の起源", "summary": "ビッグバンによる宇宙の膨張"},
    )
    event_bus.publish(event)

    assert internal_bus.publish.call_count == 1
    call_args = internal_bus.publish.call_args[0][0]
    assert isinstance(call_args, PlanDecided)
    plan = call_args.plan
    assert plan.silent is False
    assert "宇宙の起源" in plan.content
    assert "ビッグバンによる宇宙の膨張" in plan.content
    assert "システムからの内部指示" in plan.content
