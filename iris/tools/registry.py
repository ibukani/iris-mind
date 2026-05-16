from __future__ import annotations

from iris.tools.models import ToolDef


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolDef] = {}

    def register(self, tool_def: ToolDef) -> None:
        self._tools[tool_def.name] = tool_def

    def get(self, name: str) -> ToolDef | None:
        return self._tools.get(name)

    def list_tools(self) -> list[dict]:
        return [t.to_openai_tool() for t in self._tools.values()]

    def list_tools_for_role(self, role: str) -> list[dict]:
        return [t.to_openai_tool() for t in self._tools.values() if role in (t.allowed_roles or {"base", "smart"})]

    def execute(self, name: str, **kwargs: object) -> str:
        td = self.get(name)
        if td is None:
            return f"Error: tool '{name}' not found"
        return td.execute(**kwargs)

    def is_side_effect(self, name: str) -> bool:
        td = self.get(name)
        return td is not None and td.side_effect
