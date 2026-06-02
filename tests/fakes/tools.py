"""Fake ToolExecutionEngine と CapabilityRegistry。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


class FakeCapabilityRegistry:
    def __init__(self) -> None:
        self._tools: list[dict] = []
        self._side_effects: set[str] = set()

    def list_tools(self) -> list[dict]:
        return self._tools

    def register_func(
        self,
        name: str,
        description: str = "",
        parameters: dict | None = None,
        **kwargs: Any,
    ) -> Callable:
        def decorator(func: Callable) -> Callable:
            self._tools.append(
                {
                    "type": "function",
                    "function": {"name": name, "description": description, "parameters": parameters or {}},
                },
            )
            return func

        return decorator

    def execute(self, name: str, **kwargs: Any) -> str:
        return f"Executed {name} with {kwargs}"

    def register_decorated(self, fn: Any) -> None:
        pass

    def is_side_effect(self, name: str) -> bool:
        return name in self._side_effects


class FakeToolExecutionEngine:
    def __init__(self) -> None:
        self.registry = FakeCapabilityRegistry()
        self._executed_results: list[tuple[str, str, bool]] = []

    def execute_all(self, ctx: list[dict]) -> list[tuple[str, str, bool]]:
        results: list[tuple[str, str, bool]] = []
        for msg in ctx:
            if msg.get("role") == "assistant" and msg.get("tool_calls"):
                for tc in msg["tool_calls"]:
                    name = tc["function"]["name"]
                    is_side = self.registry.is_side_effect(name)
                    triple = (name, "ok", is_side)
                    results.append(triple)
                    self._executed_results.append(triple)
                    if not is_side:
                        ctx.append({"role": "tool", "content": "Result: ok", "tool_call_id": tc.get("id", "")})
        return results

    @staticmethod
    def all_side_effects(results: list[tuple[str, str, bool]]) -> bool:
        return bool(results) and all(r[2] for r in results)


__all__ = ["FakeCapabilityRegistry", "FakeToolExecutionEngine"]
