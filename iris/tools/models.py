from __future__ import annotations

from typing import Any, TypedDict

from langchain_core.tools import StructuredTool
from langchain_core.utils.function_calling import convert_to_openai_tool
from pydantic import BaseModel, ConfigDict, Field


class ToolFunctionSpec(TypedDict, total=False):
    name: str
    description: str
    parameters: dict[str, Any]
    strict: bool


class ToolSchema(TypedDict, total=False):
    """OpenAI tool_choice 互換のスキーマ。"""

    type: str
    function: ToolFunctionSpec


class ToolDef(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    name: str
    description: str
    tool: StructuredTool = Field(repr=False)
    side_effect: bool = False
    allowed_roles: set[str] | None = None

    @property
    def parameters(self) -> dict[str, Any]:
        schema = self.to_openai_tool()
        func = schema.get("function") or {}
        params = func.get("parameters")
        return params if isinstance(params, dict) else {}

    def to_openai_tool(self) -> ToolSchema:
        raw = convert_to_openai_tool(self.tool)
        return ToolSchema(
            type=raw.get("type", "function"),
            function=raw.get("function", {}),
        )

    def execute(self, **kwargs: object) -> str:
        result = self.tool.invoke(input=kwargs)
        if result is None:
            return ""
        return str(result)


class ToolResult(BaseModel):
    success: bool = True
    data: object = None
    error: str | None = None
    content: str = ""
