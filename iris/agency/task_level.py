from __future__ import annotations

from dataclasses import dataclass


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
    temperature: float | None = None


TASK_LEVELS: dict[str, TaskLevel] = {
    "chat": TaskLevel("chat", 1, "low", 80, 0, 0, False, False, False),
    "light": TaskLevel("light", 2, "low", 256, 1, 1, False, False, True),
    "normal": TaskLevel("normal", 3, "medium", 0, 5, 2, True, True, True),
    "deep": TaskLevel("deep", 4, "medium", 4096, 10, 3, True, True, True),
    "research": TaskLevel("research", 5, "high", 8192, 20, 4, True, True, True),
}
