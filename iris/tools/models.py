from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass
class ToolDef:
    name: str
    description: str
    parameters: dict
    fn: Callable
    side_effect: bool = False
    allowed_roles: set[str] | None = None

    def to_openai_tool(self) -> dict:
        required: list[str] = self.parameters.get("required", [])
        properties: dict = self.parameters.get("properties", {})
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }

    def execute(self, **kwargs: object) -> str:
        return self.fn(**kwargs)  # type: ignore[no-any-return]


@dataclass
class ToolResult:
    success: bool = True
    data: object = None
    error: str | None = None
    content: str = ""
