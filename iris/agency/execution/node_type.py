from __future__ import annotations

from dataclasses import dataclass


@dataclass
class NodeType:
    name: str
    entry_level: str
    available_levels: list[str]
    max_chain_depth: int
    routing_targets: list[str]
    tool_list_by_level: dict[str, list[str] | None]


NODE_TYPES: dict[str, NodeType] = {
    "general_chat": NodeType(
        name="general_chat",
        entry_level="chat",
        available_levels=["chat", "light"],
        max_chain_depth=10,
        routing_targets=["general_chat", "general_task", "finish"],
        tool_list_by_level={"chat": [], "light": ["web_search", "read_file"]},
    ),
    "general_task": NodeType(
        name="general_task",
        entry_level="normal",
        available_levels=["normal", "deep", "research"],
        max_chain_depth=3,
        routing_targets=["general_chat", "general_task", "deep_task", "finish"],
        tool_list_by_level={"normal": None, "deep": None, "research": None},
    ),
}

ROUTING_TOOLS: dict[str, dict[str, str]] = {
    "general_chat": {
        "description": "Continue with another short message to say more.",
    },
    "general_task": {
        "description": "Switch to task mode with full tool access for multi-step work.",
    },
    "deep_task": {
        "description": "Upgrade to extended mode for complex tasks needing more tokens or tool rounds.",
    },
    "finish": {
        "description": "Complete the response when no more actions are needed.",
    },
}
