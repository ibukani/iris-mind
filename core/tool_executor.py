from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.llm_bridge import LLMBridge
    from capabilities.registry import CapabilityRegistry


class ToolExecutionEngine:
    """Tool Call の実行と事後処理を共通化するエンジン。

    Executor（Plan-and-Execute 内の ReAct ループ）と
    CliSession（通常会話内の Tool Call 処理）の両方から利用する。
    """

    def __init__(self, llm: LLMBridge, registry: CapabilityRegistry):
        self.llm = llm
        self.registry = registry

    def execute_all(self, ctx: list[dict]) -> list[tuple[str, str]]:
        """ctx 末尾のメッセージに含まれる tool_calls をすべて実行し、ctx に追跡する。

        Returns:
            [(func_name, result), ...] のリスト
        """
        last = ctx[-1]
        if not last.get("tool_calls"):
            return []

        results: list[tuple[str, str]] = []
        for tc in last["tool_calls"]:
            func_name = tc["function"]["name"]
            args = tc["function"]["arguments"]
            result = self.registry.execute(func_name, **args)
            ctx.append({
                "role": "tool",
                "name": func_name,
                "content": result,
            })
            results.append((func_name, result))
        return results

    def should_follow_up(self, tool_results: list[tuple[str, str]]) -> bool:
        """Tool 実行結果にエラーや長大な結果が含まれるか判定。"""
        for _, result in tool_results:
            if len(result) > 200:
                return True
            lower = result.lower()
            if any(w in lower for w in ("error", "fail", "exception", "traceback")):
                return True
        return False
