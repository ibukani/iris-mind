from __future__ import annotations
import json
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from core.llm_bridge import LLMBridge
    from capabilities.registry import CapabilityRegistry


class Executor:
    """サブタスク逐次実行エンジン。Plan-and-Execute の実行フェーズ。"""

    def __init__(self, llm: LLMBridge, registry: CapabilityRegistry):
        self.llm = llm
        self.registry = registry

    def execute_plan(self, plan: dict, user_input: str, personality_name: str = "Iris",
                     on_subtask: Callable[[int, str], None] | None = None) -> list[dict]:
        subtasks = plan.get("subtasks", [])
        results: list[dict] = []

        for i, task in enumerate(subtasks):
            name = task.get("name", f"step_{i}")
            if on_subtask:
                on_subtask(i, name)
            desc = task.get("description", "")
            step_prompt = (
                f"あなたは{personality_name}です。与えられたタスクを正確に実行してください。\n\n"
                f"## Current Task ({i+1}/{len(subtasks)})\n"
                f"Task: {name}\n"
                f"Description: {desc}\n"
                f"Original request: {user_input}"
            )

            messages = [{"role": "user", "content": f"Execute this task: {desc}"}]
            step_result = self._run_react(step_prompt, messages)
            results.append({"name": name, "output": step_result})

        return results

    def synthesize(self, plan: dict, results: list[dict], user_input: str, personality_name: str = "Iris") -> str:
        summary_lines = []
        for r in results:
            summary_lines.append(f"### {r['name']}\n{r['output'][:500]}")
        summary = "\n\n".join(summary_lines)

        sys_prompt = (
            f"あなたは{personality_name}です。マルチステップ計画の実行結果を"
            f"ユーザーにわかりやすく要約してください。"
        )
        resp = self.llm.chat(
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content":
                 f"I executed a multi-step plan. Summarize the results:\n\n"
                 f"## Original Request\n{user_input}\n\n"
                 f"## Plan\n{json.dumps(plan, ensure_ascii=False)}\n\n"
                 f"## Results\n{summary}"},
            ],
            temperature=0.5,
            max_tokens=1000,
        )
        return resp["message"].get("content", "").strip()

    def _run_react(self, system_prompt: str, messages: list[dict], max_turns: int = 3) -> str:
        tools = self.registry.list_tools()
        ctx = list(messages)

        for _ in range(max_turns):
            resp = self.llm.chat(
                messages=[{"role": "system", "content": system_prompt}, *ctx],
                tools=tools,
                temperature=0.5,
                max_tokens=1000,
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
                )
                msg = final["message"]
                ctx.append(msg)

            content = msg.get("content", "").strip()
            if content:
                return content

        return "(completed with no output)"
