from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from iris.tools.decorator import get_tool_def
from iris.tools.registry import ToolRegistry


class Capability:
    def __init__(
        self,
        name: str,
        description: str,
        parameters: dict,
        func: Callable,
        allowed_roles: set[str] | None = None,
    ) -> None:
        self.name = name
        self.description = description
        self.parameters = parameters
        self.func = func
        self.allowed_roles = allowed_roles or {"base", "smart"}

    def to_openai_tool(self) -> dict:
        required: list[str] = []
        clean_params: dict = {}
        for k, v in self.parameters.items():
            if v.get("required"):
                required.append(k)
            clean_params[k] = {kk: vv for kk, vv in v.items() if kk != "required"}
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": clean_params,
                    "required": required,
                },
            },
        }

    def execute(self, **kwargs: object) -> str:
        return self.func(**kwargs)


class CapabilityRegistry:
    def __init__(self) -> None:
        self._capabilities: dict[str, Capability] = {}
        self.tool_registry = ToolRegistry()

    def register(self, capability: Capability) -> None:
        self._capabilities[capability.name] = capability

    def register_func(
        self,
        name: str | None = None,
        description: str | None = None,
        parameters: dict | None = None,
        allowed_roles: set[str] | None = None,
    ) -> Callable:
        def decorator(func: Callable) -> Callable:
            c = Capability(
                name=name or func.__name__,
                description=description or (func.__doc__ or "").strip(),
                parameters=parameters or {},
                func=func,
                allowed_roles=allowed_roles,
            )
            self.register(c)
            return func

        return decorator

    def register_decorated(self, fn: Callable) -> None:
        td = get_tool_def(fn)
        if td is None:
            raise ValueError(f"Function {fn.__name__} has no _tool_def. Use @tool decorator.")
        self.tool_registry.register(td)

    def get(self, name: str) -> Capability | None:
        return self._capabilities.get(name)

    def list_tools(self) -> list[dict]:
        old = [c.to_openai_tool() for c in self._capabilities.values()]
        new = self.tool_registry.list_tools()
        names = {t["function"]["name"] for t in old}
        for t in new:
            if t["function"]["name"] not in names:
                old.append(t)
        return old

    def list_tools_for_role(self, role: str) -> list[dict]:
        result = [c.to_openai_tool() for c in self._capabilities.values() if role in c.allowed_roles]
        known = {t["function"]["name"] for t in result}
        for t in self.tool_registry.list_tools():
            td = self.tool_registry.get(t["function"]["name"])
            if td and t["function"]["name"] not in known and role in (td.allowed_roles or {"base", "smart"}):
                result.append(t)
        return result

    def execute(self, name: str, **kwargs: object) -> str:
        cap = self.get(name)
        if cap:
            return cap.execute(**kwargs)
        return self.tool_registry.execute(name, **kwargs)

    def is_side_effect(self, name: str) -> bool:
        return self.tool_registry.is_side_effect(name)

    def discover_modules(
        self,
        base_paths: list[str] | None = None,
    ) -> None:
        if base_paths is None:
            base_paths = ["iris/capabilities"]

        import importlib

        for base in base_paths:
            p = Path(base).resolve()
            if not p.is_dir():
                continue
            base_module = base.replace("/", ".").replace("\\", ".")
            for module_file in p.rglob("*.py"):
                if module_file.name != "server.py":
                    continue
                rel = module_file.relative_to(p)
                relative_module = str(rel.with_suffix("")).replace("/", ".").replace("\\", ".")
                module_path = f"{base_module}.{relative_module}"
                try:
                    mod = importlib.import_module(module_path)
                    if hasattr(mod, "register"):
                        mod.register(self)
                except Exception as e:
                    import logging

                    logging.getLogger(__name__).warning(
                        "Failed to load capability %s: %s",
                        module_path,
                        e,
                    )
