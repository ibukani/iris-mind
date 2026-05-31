from __future__ import annotations

from dataclasses import dataclass, field

from langchain_core.tools import StructuredTool
from langchain_core.utils.function_calling import convert_to_openai_tool


@dataclass
class ToolDef:
    name: str
    description: str
    tool: StructuredTool = field(repr=False)
    side_effect: bool = False
    allowed_roles: set[str] | None = None

    @property
    def parameters(self) -> dict:
        return self.to_openai_tool()["function"]["parameters"]  # type: ignore[no-any-return]

    def to_openai_tool(self) -> dict:
        return convert_to_openai_tool(self.tool)

    def execute(self, **kwargs: object) -> str:
        result = self.tool.invoke(input=kwargs)
        if result is None:
            return ""
        return str(result)


@dataclass
class ToolResult:
    success: bool = True
    data: object = None
    error: str | None = None
    content: str = ""
