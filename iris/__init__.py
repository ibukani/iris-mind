"""
Iris v0.3 — 3-Process アーキテクチャ (Input / Kernel / Output)
"""

from iris.kernel.agent_state import AgentStateManager
from iris.kernel.agent_state import State as AgentState
from iris.kernel.config import Config, ProactiveConfig
from iris.kernel.event_bus import (
    AgentAnomalyEvent,
    AgentResponseEvent,
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
    "AgentResponseEvent",
    "AgentAnomalyEvent",
    "MemoryUpdateEvent",
    "AgentStateManager",
    "AgentState",
]
