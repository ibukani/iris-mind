from __future__ import annotations

from typing import Any

LEVEL_PROFILES: dict[int, dict[str, Any]] = {
    1: {
        "model_role": "fast",
        "abbreviated": True,
        "tools_allowed": False,
        "allow_side_effects": False,
        "max_tokens": 80,
        "temperature": 0.5,
        "show_thinking": False,
        "run_reflexion": False,
        "run_compression": False,
        "priority": 0,
        "max_tool_iterations": 1,
    },
    2: {
        "model_role": "default",
        "abbreviated": False,
        "tools_allowed": True,
        "allow_side_effects": True,
        "max_tokens": 0,
        "temperature": 0.7,
        "show_thinking": False,
        "run_reflexion": False,
        "run_compression": True,
        "priority": 0,
        "max_tool_iterations": 3,
    },
    3: {
        "model_role": "default",
        "abbreviated": False,
        "tools_allowed": True,
        "allow_side_effects": True,
        "max_tokens": 0,
        "temperature": 0.7,
        "show_thinking": True,
        "run_reflexion": True,
        "run_compression": True,
        "priority": 1,
        "max_tool_iterations": 3,
    },
    4: {
        "model_role": "default",
        "abbreviated": False,
        "tools_allowed": True,
        "allow_side_effects": True,
        "max_tokens": 4096,
        "temperature": 0.8,
        "show_thinking": True,
        "run_reflexion": True,
        "run_compression": True,
        "priority": 2,
        "max_tool_iterations": 5,
    },
    5: {
        "model_role": "default",
        "abbreviated": False,
        "tools_allowed": True,
        "allow_side_effects": True,
        "max_tokens": 8192,
        "temperature": 0.9,
        "show_thinking": True,
        "run_reflexion": True,
        "run_compression": True,
        "priority": 3,
        "max_tool_iterations": 10,
    },
}


def resolve_level(level: int, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    profile = LEVEL_PROFILES.get(level, LEVEL_PROFILES[2])
    result = dict(profile)
    if overrides:
        result.update(overrides)
    return result
