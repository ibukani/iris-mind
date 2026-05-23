from __future__ import annotations

from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from loguru import logger

from iris.tools.registry import ToolRegistry


class ToolEngine:
    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry

    def run_tool_calls(self, ctx: list[BaseMessage]) -> list[tuple[str, str, bool]]:
        last = ctx[-1]
        if not isinstance(last, AIMessage) or not getattr(last, "tool_calls", None):
            return []

        results: list[tuple[str, str, bool]] = []
        for tc in last.tool_calls:
            func_name = tc["name"]
            args: dict = tc.get("args", {})
            tool_call_id = tc.get("id", "unknown")
            is_side = self.registry.is_side_effect(func_name)
            logger.info("ToolExec: executing {} side_effect={} args={}", func_name, is_side, _truncate_args(args))
            result = self.registry.execute(func_name, **args)
            if not is_side:
                ctx.append(
                    ToolMessage(
                        name=func_name,
                        content=result,
                        tool_call_id=tool_call_id,
                    )
                )
            results.append((func_name, result, is_side))
            logger.info("ToolExec: {} done (result len={})", func_name, len(result))
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
