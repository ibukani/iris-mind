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
from iris.agency.planning.context_hint_builder import ContextHintBuilder
from iris.agency.planning.decisions import ProactiveJudge
from iris.agency.planning.question_generator import QuestionGenerator
from iris.agency.planning.strategies import ProactivePlanStrategy, ResponsePlanStrategy
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

    context_builder = ContextHintBuilder(memory=None)
    question_gen = QuestionGenerator(llm=llm)

    judge = ProactiveJudge(
        scoring=scoring,
        config=config.proactive,
        context_builder=context_builder,
    )
    proactive_strategy = ProactivePlanStrategy(question_gen=question_gen)
    response_strategy = ResponsePlanStrategy(
        config=config.proactive,
        context_builder=context_builder,
    )

    PlanningManager(
        internal_bus=internal_bus,
        proactive_judge=judge,
        proactive_strategy=proactive_strategy,
        response_strategy=response_strategy,
    )

    from iris.agency.planning.handler import _PlanningEventHandler

    _PlanningEventHandler(
        event_bus=event_bus,
        internal_bus=internal_bus,
        proactive_judge=judge,
        proactive_strategy=proactive_strategy,
        response_strategy=response_strategy,
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

    context_builder = ContextHintBuilder(memory=None)

    judge = ProactiveJudge(
        scoring=scoring,
        config=config.proactive,
        context_builder=context_builder,
    )
    proactive_strategy = ProactivePlanStrategy(question_gen=None)
    response_strategy = ResponsePlanStrategy(
        config=config.proactive,
        context_builder=context_builder,
    )

    PlanningManager(
        internal_bus=internal_bus,
        proactive_judge=judge,
        proactive_strategy=proactive_strategy,
        response_strategy=response_strategy,
    )

    from iris.agency.planning.handler import _PlanningEventHandler

    _PlanningEventHandler(
        event_bus=event_bus,
        internal_bus=internal_bus,
        proactive_judge=judge,
        proactive_strategy=proactive_strategy,
        response_strategy=response_strategy,
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
    assert "調査" in plan.content
