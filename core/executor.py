from __future__ import annotations
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from core.llm_bridge import LLMBridge
    from capabilities.registry import CapabilityRegistry


class Executor:
    """サブタスク逐次実行エンジン。Plan-and-Execute の実行フェーズ。"""

    def __init__(self, llm: LLMBridge, registry: CapabilityRegistry):
        self.llm = llm
        self.registry = registry

    def execute_plan(self, plan: dict, user_input: str, personality_name: str = "Iris",
                     on_subtask: Callable[[int, str], None] | None = None) -> str:
        subtasks = plan.get("subtasks", [])
        results: list[dict] = []

        for i, task in enumerate(subtasks):
            name = task.get("name", f"step_{i}")
            if on_subtask:
                on_subtask(i, name)
            desc = task.get("description", "")
            is_last = (i == len(subtasks) - 1)

            step_prompt = (
                f"あなたは{personality_name}です。与えられたタスクを正確に実行してください。\n\n"
                f"## Current Task ({i+1}/{len(subtasks)})\n"
                f"Task: {name}\n"
                f"Description: {desc}\n"
                f"Original request: {user_input}"
            )

            if is_last and len(subtasks) > 1 and results:
                summaries = "\n".join(
                    f"- {r['name']}: {r['output'][:300]}"
                    for r in results
                )
                step_prompt += (
                    f"\n\n## Previous Steps Results\n{summaries}\n\n"
                    f"This is the final step. Synthesize all previous steps "
                    f"and present the complete results to the user."
                )

            messages = [{"role": "user", "content": f"Execute this task: {desc}"}]
            step_result = self._run_react(step_prompt, messages)
            results.append({"name": name, "output": step_result})

        if not results:
            return ""
        return results[-1]["output"]

    def _run_react(self, system_prompt: str, messages: list[dict], max_turns: int = 3) -> str:
        tools = self.registry.list_tools()
        ctx = list(messages)

        for _ in range(max_turns):
            resp = self.llm.chat(
                messages=[{"role": "system", "content": system_prompt}, *ctx],
                tools=tools,
                temperature=0.5,
                max_tokens=1000,
                keep_alive="0",
            )
            msg = resp["message"]
            ctx.append(msg)

            if msg.get("tool_calls"):
                for tc in msg["tool_calls"]:
                    func_name = tc["function"]["name"]
                    args = tc["function"]["arguments"]
                    result = self.registry.execute(func_name, **args)
                    ctx.append({
                        "role": "tool",
                        "name": func_name,
                        "content": result,
                    })

                final = self.llm.chat(
                    messages=[{"role": "system", "content": system_prompt}, *ctx],
                    temperature=0.5,
                    max_tokens=1000,
                    keep_alive="0",
                )
                msg = final["message"]
                ctx.append(msg)

            content = msg.get("content", "").strip()
            if content:
                return content

        return "(completed with no output)"
