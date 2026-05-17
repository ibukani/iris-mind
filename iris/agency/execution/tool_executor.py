from __future__ import annotations

from iris.tools.registry import ToolRegistry


class ToolExecutionEngine:
    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry

    def execute_all(self, ctx: list[dict]) -> list[tuple[str, str, bool]]:
        last = ctx[-1]
        if not last.get("tool_calls"):
            return []

        results: list[tuple[str, str, bool]] = []
        for tc in last["tool_calls"]:
            func_name = tc["function"]["name"]
            args: dict = tc["function"].get("arguments", {})
            is_side = self.registry.is_side_effect(func_name)
            result = self.registry.execute(func_name, **args)
            if not is_side:
                ctx.append(
                    {
                        "role": "tool",
                        "name": func_name,
                        "content": result,
                    }
                )
            results.append((func_name, result, is_side))
        return results

    @staticmethod
    def all_side_effects(results: list[tuple[str, str, bool]]) -> bool:
        return bool(results) and all(r[2] for r in results)
