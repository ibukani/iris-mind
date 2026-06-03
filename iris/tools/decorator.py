from __future__ import annotations

from collections.abc import Callable
from typing import Any

from langchain_core.tools import StructuredTool

from iris.tools.models import ToolDef


def get_tool_def(fn: Callable) -> ToolDef | None:
    return getattr(fn, "_tool_def", None)


def tool(
    name: str | None = None,
    description: str | None = None,
    side_effect: bool = False,
    allowed_roles: set[str] | None = None,
) -> Callable[[Callable], Callable]:
    def decorator(fn: Callable) -> Callable:
        structured = StructuredTool.from_function(
            func=fn,
            name=name or fn.__name__,
            description=description or (fn.__doc__ or "").strip(),
        )
        td = ToolDef(
            name=structured.name,
            description=structured.description,
            tool=structured,
            side_effect=side_effect,
            allowed_roles=allowed_roles,
        )
        fn._tool_def = td  # type: ignore[attr-defined]
        return fn

    return decorator


def register_decorated_tools(module: object, registry: Any) -> None:
    for _name in dir(module):
        obj = getattr(module, _name)
        if hasattr(obj, "_tool_def"):
            registry.register_decorated(obj)


def register_tools(registry: Any, *functions: Callable) -> None:
    for fn in functions:
        registry.register_decorated(fn)
