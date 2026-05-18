from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from iris.tools.decorator import get_tool_def
from iris.tools.models import ToolDef

logger = logging.getLogger(__name__)


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolDef] = {}

    def register(self, tool_def: ToolDef) -> None:
        self._tools[tool_def.name] = tool_def

    def register_decorated(self, fn: Callable) -> None:
        td = get_tool_def(fn)
        if td is None:
            raise ValueError("Function has no _tool_def. Use @tool decorator.")
        self.register(td)

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

    def discover_modules(self, base_paths: list[str] | None = None) -> None:
        if base_paths is None:
            base_paths = ["iris/tools/builtins"]

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
                    logger.warning("Failed to load tool module %s: %s", module_path, e)
