from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TaskLevel:
    name: str
    order: int
    model_role: str
    max_tokens: int
    max_tool_iterations: int
    priority: int
    show_thinking: bool
    run_reflexion: bool
    run_compression: bool


TASK_LEVELS: dict[str, TaskLevel] = {
    "chat": TaskLevel("chat", 1, "fast", 80, 0, 0, False, False, False),
    "light": TaskLevel("light", 2, "fast", 256, 1, 1, False, False, True),
    "normal": TaskLevel("normal", 3, "default", 0, 5, 2, True, True, True),
    "deep": TaskLevel("deep", 4, "default", 4096, 10, 3, True, True, True),
    "research": TaskLevel("research", 5, "smart", 8192, 20, 4, True, True, True),
}


def resolve_level(name: str, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    tl = TASK_LEVELS[name]
    result: dict[str, Any] = {
        "task_level": tl.name,
        "model_role": tl.model_role,
        "max_tokens": tl.max_tokens,
        "max_tool_iterations": tl.max_tool_iterations,
        "priority": tl.priority,
        "show_thinking": tl.show_thinking,
        "run_reflexion": tl.run_reflexion,
        "run_compression": tl.run_compression,
    }
    if overrides:
        result.update(overrides)
    return result
