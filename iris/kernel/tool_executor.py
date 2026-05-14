"""
ToolExecutionEngine — Tool Call の実行と事後処理。

ConversationService から利用され、LLM が生成した tool_calls を
CapabilityRegistry 経由で実行し、結果を会話コンテキストに追跡する。
"""

from __future__ import annotations

from typing import Any


class ToolExecutionEngine:
    """Tool Call の実行と事後処理を共通化するエンジン。"""

    def __init__(self, registry: Any) -> None:
        self.registry = registry

    def execute_all(self, ctx: list[dict]) -> list[tuple[str, str]]:
        """
        ctx 末尾のメッセージに含まれる tool_calls をすべて実行し、
        結果を ctx に追跡する。

        Returns:
            [(func_name, result), ...] のリスト
        """
        last = ctx[-1]
        if not last.get("tool_calls"):
            return []

        results: list[tuple[str, str]] = []
        for tc in last["tool_calls"]:
            func_name = tc["function"]["name"]
            args: dict = tc["function"].get("arguments", {})
            result = self.registry.execute(func_name, **args)
            ctx.append(
                {
                    "role": "tool",
                    "name": func_name,
                    "content": result,
                }
            )
            results.append((func_name, result))
        return results

    @staticmethod
    def should_follow_up(tool_results: list[tuple[str, str]]) -> bool:
        """Tool 実行結果にエラーや長大な結果が含まれるか判定する。"""
        for _, result in tool_results:
            if len(result) > 200:
                return True
            lower = result.lower()
            if any(w in lower for w in ("error", "fail", "exception", "traceback")):
                return True
        return False
