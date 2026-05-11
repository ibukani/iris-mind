from __future__ import annotations
from pathlib import Path
from typing import Any, Callable


class Capability:
    def __init__(
        self,
        name: str,
        description: str,
        parameters: dict,
        func: Callable,
    ):
        self.name = name
        self.description = description
        self.parameters = parameters
        self.func = func

    def to_openai_tool(self) -> dict:
        required = []
        clean_params = {}
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

    def execute(self, **kwargs) -> str:
        return self.func(**kwargs)


class CapabilityRegistry:
    """全capabilityを一元管理するレジストリ"""

    def __init__(self):
        self._capabilities: dict[str, Capability] = {}

    def register(self, capability: Capability):
        self._capabilities[capability.name] = capability

    def register_func(
        self,
        name: str | None = None,
        description: str | None = None,
        parameters: dict | None = None,
    ):
        def decorator(func):
            c = Capability(
                name=name or func.__name__,
                description=description or (func.__doc__ or "").strip(),
                parameters=parameters or {},
                func=func,
            )
            self.register(c)
            return func
        return decorator

    def get(self, name: str) -> Capability | None:
        return self._capabilities.get(name)

    def list_tools(self) -> list[dict]:
        return [c.to_openai_tool() for c in self._capabilities.values()]

    def execute(self, name: str, **kwargs) -> str:
        cap = self.get(name)
        if not cap:
            return f"Error: capability '{name}' not found"
        return cap.execute(**kwargs)

    def discover_modules(self, base_path: str = "capabilities"):
        """capabilities/ 以下のserver.pyを動的に発見・登録"""
        p = Path(base_path).resolve()
        for server_file in p.rglob("server.py"):
            rel = server_file.relative_to(p.parent)
            module_path = str(rel.with_suffix("")).replace("/", ".").replace("\\", ".")
            try:
                import importlib
                mod = importlib.import_module(module_path)
                if hasattr(mod, "register"):
                    mod.register(self)
            except Exception as e:
                print(f"Warning: failed to load {module_path}: {e}")
