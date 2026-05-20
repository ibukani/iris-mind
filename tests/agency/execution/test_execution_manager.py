from __future__ import annotations

import time
from unittest.mock import MagicMock

from iris.agency.bus import InternalBus
from iris.agency.execution.manager import ExecutionManager
from iris.event.event_bus import EventBus
from iris.event.event_types import TimerTick
from iris.kernel.config import Config, ProactiveConfig


def test_execution_manager_idle_reflection_triggers() -> None:
    # 準備
    internal_bus = MagicMock(spec=InternalBus)
    event_bus = EventBus()
    llm_pipeline = MagicMock()
    hippocampal = MagicMock()

    config = MagicMock(spec=Config)
    proactive = ProactiveConfig(idle_reflection_timeout_sec=2.0)
    config.proactive = proactive

    manager = ExecutionManager(
        internal_bus=internal_bus,
        event_bus=event_bus,
        llm_pipeline=llm_pipeline,
        hippocampal=hippocampal,
        config=config,
    )

    manager._msg_count_since_reflect = 1
    manager._messages.append({"role": "user", "content": "hello"})
    manager._last_activity_time = time.time() - 2.1

    # TimerTick発行
    event_bus.publish(
        TimerTick(
            timestamp=None,
            source="test",
            tick_count=1,
        )
    )

    # スレッド完了を待つ
    time.sleep(0.1)

    # 検証
    hippocampal.force_run.assert_called_once_with(manager._messages)
    assert manager._msg_count_since_reflect == 0


def test_execution_manager_idle_reflection_no_trigger_if_zero_count() -> None:
    # 準備
    internal_bus = MagicMock(spec=InternalBus)
    event_bus = EventBus()
    llm_pipeline = MagicMock()
    hippocampal = MagicMock()

    config = MagicMock(spec=Config)
    proactive = ProactiveConfig(idle_reflection_timeout_sec=2.0)
    config.proactive = proactive

    manager = ExecutionManager(
        internal_bus=internal_bus,
        event_bus=event_bus,
        llm_pipeline=llm_pipeline,
        hippocampal=hippocampal,
        config=config,
    )

    manager._msg_count_since_reflect = 0
    manager._last_activity_time = time.time() - 2.1

    event_bus.publish(TimerTick(timestamp=None, source="test", tick_count=1))
    time.sleep(0.1)

    hippocampal.force_run.assert_not_called()


def test_execution_manager_idle_reflection_no_trigger_if_not_timeout() -> None:
    # 準備
    internal_bus = MagicMock(spec=InternalBus)
    event_bus = EventBus()
    llm_pipeline = MagicMock()
    hippocampal = MagicMock()

    config = MagicMock(spec=Config)
    proactive = ProactiveConfig(idle_reflection_timeout_sec=2.0)
    config.proactive = proactive

    manager = ExecutionManager(
        internal_bus=internal_bus,
        event_bus=event_bus,
        llm_pipeline=llm_pipeline,
        hippocampal=hippocampal,
        config=config,
    )

    manager._msg_count_since_reflect = 1
    manager._last_activity_time = time.time() - 1.0  # 1秒しか経過していない

    event_bus.publish(TimerTick(timestamp=None, source="test", tick_count=1))
    time.sleep(0.1)

    hippocampal.force_run.assert_not_called()
    assert manager._msg_count_since_reflect == 1
