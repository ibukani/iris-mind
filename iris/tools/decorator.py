from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any, get_args, get_origin, get_type_hints

from iris.tools.models import ToolDef


def _type_to_json(t: type) -> dict:
    if t is str:
        return {"type": "string"}
    if t is int:
        return {"type": "integer"}
    if t is float:
        return {"type": "number"}
    if t is bool:
        return {"type": "boolean"}
    return {"type": "string"}


def _generate_schema(fn: Callable, descriptions: dict[str, str] | None = None) -> dict:
    hints = get_type_hints(fn)
    sig = inspect.signature(fn)
    properties: dict[str, dict] = {}
    required: list[str] = []

    for name, param in sig.parameters.items():
        if name == "return":
            continue

        hint = hints.get(name, str)
        origin = get_origin(hint)
        js: dict | None = None

        if origin is not None:
            args = get_args(hint)
            if type(None) in args:
                non_none = [a for a in args if a is not type(None)]
                actual = non_none[0] if non_none else str
                js = _type_to_json(actual)
                js["nullable"] = True
            else:
                js = {"type": "string"}
        else:
            js = _type_to_json(hint)

        if descriptions and name in descriptions:
            js["description"] = descriptions[name]

        if param.default is inspect.Parameter.empty:
            required.append(name)
        else:
            dv = param.default
            if not isinstance(dv, type):
                js["default"] = dv

        properties[name] = js

    return {
        "type": "object",
        "properties": properties,
        "required": required,
    }


def get_tool_def(fn: Callable) -> ToolDef | None:
    return getattr(fn, "_tool_def", None)


def tool(
    name: str | None = None,
    description: str | None = None,
    side_effect: bool = False,
    allowed_roles: set[str] | None = None,
    descriptions: dict[str, str] | None = None,
) -> Callable[[Callable], Callable]:
    def decorator(fn: Callable) -> Callable:
        td = ToolDef(
            name=name or fn.__name__,
            description=description or (fn.__doc__ or "").strip(),
            parameters=_generate_schema(fn, descriptions=descriptions),
            fn=fn,
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
