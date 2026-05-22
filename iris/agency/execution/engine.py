from __future__ import annotations

import logging

from iris.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


class ToolEngine:
    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry

    def run_tool_calls(self, ctx: list[dict]) -> list[tuple[str, str, bool]]:
        last = ctx[-1]
        if not last.get("tool_calls"):
            return []

        results: list[tuple[str, str, bool]] = []
        for tc in last["tool_calls"]:
            func_name = tc["function"]["name"]
            args: dict = tc["function"].get("arguments", {})
            is_side = self.registry.is_side_effect(func_name)
            logger.info("ToolExec: executing %s side_effect=%s args=%s", func_name, is_side, _truncate_args(args))
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
            logger.info("ToolExec: %s done (result len=%d)", func_name, len(result))
        return results

    @staticmethod
    def all_side_effect(results: list[tuple[str, str, bool]]) -> bool:
        return bool(results) and all(r[2] for r in results)


def _truncate_args(args: dict, max_len: int = 200) -> dict:
    truncated = {}
    for k, v in args.items():
        if isinstance(v, str) and len(v) > max_len:
            truncated[k] = v[:max_len] + "..."
        else:
            truncated[k] = v
    return truncated
