from __future__ import annotations

import time
from unittest.mock import MagicMock

from iris.agency.bus import InternalBus
from iris.agency.execution.executor import FlowExecutor
from iris.agency.execution.regulation.consolidator import Consolidator
from iris.event.event_bus import EventBus
from iris.event.event_types import TimerTick
from iris.kernel.config import Config, ProactiveConfig


def test_execution_manager_idle_reflection_triggers() -> None:
    internal_bus = MagicMock(spec=InternalBus)
    event_bus = EventBus()
    llm_pipeline = MagicMock()
    hippocampal = MagicMock()

    config = MagicMock(spec=Config)
    proactive = ProactiveConfig(idle_reflection_timeout_sec=2.0)
    config.proactive = proactive

    consolidator = Consolidator(
        event_bus=event_bus,
        messages_getter=lambda: manager._messages,
        hippocampal=hippocampal,
        config=config,
    )
    manager = FlowExecutor(
        internal_bus=internal_bus,
        event_bus=event_bus,
        llm_pipeline=llm_pipeline,
        consolidator=consolidator,
    )

    manager._messages.append({"role": "user", "content": "hello"})
    manager._consolidator._msg_count_since_reflect = 1
    manager._consolidator._last_activity_time = time.time() - 2.1

    event_bus.publish(
        TimerTick(
            timestamp=None,
            source="test",
            tick_count=1,
        )
    )

    time.sleep(0.1)

    hippocampal.force_run.assert_called_once()
    assert manager._consolidator._msg_count_since_reflect == 0


def test_execution_manager_idle_reflection_no_trigger_if_zero_count():
    internal_bus = MagicMock()
    event_bus = EventBus()
    llm_pipeline = MagicMock()
    hippocampal = MagicMock()

    config = MagicMock()
    proactive = ProactiveConfig(idle_reflection_timeout_sec=2.0)
    config.proactive = proactive

    consolidator = Consolidator(
        event_bus=event_bus,
        messages_getter=lambda: manager._messages,
        hippocampal=hippocampal,
        config=config,
    )
    manager = FlowExecutor(
        internal_bus=internal_bus,
        event_bus=event_bus,
        llm_pipeline=llm_pipeline,
        consolidator=consolidator,
    )

    manager._consolidator._msg_count_since_reflect = 0
    manager._consolidator._last_activity_time = time.time() - 2.1

    event_bus.publish(TimerTick(timestamp=None, source="test", tick_count=1))
    time.sleep(0.1)

    hippocampal.force_run.assert_not_called()


def test_execution_manager_idle_reflection_no_trigger_if_not_timeout() -> None:
    internal_bus = MagicMock(spec=InternalBus)
    event_bus = EventBus()
    llm_pipeline = MagicMock()
    hippocampal = MagicMock()

    config = MagicMock(spec=Config)
    proactive = ProactiveConfig(idle_reflection_timeout_sec=2.0)
    config.proactive = proactive

    consolidator = Consolidator(
        event_bus=event_bus,
        messages_getter=lambda: manager._messages,
        hippocampal=hippocampal,
        config=config,
    )
    manager = FlowExecutor(
        internal_bus=internal_bus,
        event_bus=event_bus,
        llm_pipeline=llm_pipeline,
        consolidator=consolidator,
    )

    manager._consolidator._msg_count_since_reflect = 1
    manager._consolidator._last_activity_time = time.time() - 1.0

    event_bus.publish(TimerTick(timestamp=None, source="test", tick_count=1))
    time.sleep(0.1)

    hippocampal.force_run.assert_not_called()
    assert manager._consolidator._msg_count_since_reflect == 1
