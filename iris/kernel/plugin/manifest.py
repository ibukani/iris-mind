from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, IntEnum


class PluginCategory(Enum):
    CORE = "core"
    LAYER = "layer"
    FEATURE = "feature"
    PROVIDER = "provider"
    TOOL = "tool"


class PluginPhase(IntEnum):
    INFRA = 0
    CORE = 10
    STORE = 15
    LAYER = 20
    COGNITIVE = 30
    FEATURE = 40
    READY = 50


class PluginState(Enum):
    UNLOADED = "unloaded"
    INITIALIZED = "initialized"
    STARTED = "started"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass
class PluginManifest:
    name: str
    version: str
    category: PluginCategory
    phase: PluginPhase
    dependencies: set[str] = field(default_factory=set)
    provides: list[str] = field(default_factory=list)
    description: str = ""
