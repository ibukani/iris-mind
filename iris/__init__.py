"""
Iris v0.2 — メインパッケージ（新規実装分のみ）

移行期間中は旧 core/ / memory/ / capabilities/ がそのまま機能する。
iris/ 配下は段階的に実装を移す。
"""

from iris.kernel.agent_state import AgentStateManager
from iris.kernel.agent_state import State as AgentState
from iris.kernel.config import Config, ProactiveConfig
from iris.kernel.event_bus import (
    AgentStateChangeEvent,
    Event,
    EventBus,
    MemoryUpdateEvent,
    ProactiveSpeechEvent,
    TimerTick,
    UserInputEvent,
)

__all__ = [
    "Config",
    "ProactiveConfig",
    "EventBus",
    "Event",
    "UserInputEvent",
    "ProactiveSpeechEvent",
    "TimerTick",
    "AgentStateChangeEvent",
    "MemoryUpdateEvent",
    "AgentStateManager",
    "AgentState",
]
