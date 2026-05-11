from __future__ import annotations
import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.llm_bridge import LLMBridge
    from capabilities.registry import CapabilityRegistry


class Executor:
    """サブタスク逐次実行エンジン。Plan-and-Execute の実行フェーズ。"""

    def __init__(self, llm: LLMBridge, registry: CapabilityRegistry):
        self.llm = llm
        self.registry = registry

    def execute_plan(self, plan: dict, system_prompt: str) -> list[dict]:
        subtasks = plan.get("subtasks", [])
        results: list[dict] = []

        for i, task in enumerate(subtasks):
            name = task.get("name", f"step_{i}")
            desc = task.get("description", "")
            step_prompt = f"{system_prompt}\n\n## Current Task ({i+1}/{len(subtasks)})\n{name}: {desc}"

            messages = [{"role": "user", "content": f"Execute this task: {desc}"}]
            step_result = self._run_react(step_prompt, messages)
            results.append({"name": name, "output": step_result})

        return results

    def synthesize(self, plan: dict, results: list[dict], system_prompt: str) -> str:
        summary_lines = []
        for r in results:
            summary_lines.append(f"### {r['name']}\n{r['output'][:500]}")
        summary = "\n\n".join(summary_lines)

        resp = self.llm.chat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content":
                 f"I executed a multi-step plan. Summarize the results:\n\n"
                 f"## Plan\n{json.dumps(plan, ensure_ascii=False)}\n\n"
                 f"## Results\n{summary}"},
            ],
            temperature=0.5,
            max_tokens=1000,
        )
        return resp["message"].get("content", "").strip()

    def _run_react(self, system_prompt: str, messages: list[dict], max_turns: int = 3) -> str:
        tools = self.registry.list_tools()

        for _ in range(max_turns):
            resp = self.llm.chat(
                messages=[{"role": "system", "content": system_prompt}, *messages],
                tools=tools,
                temperature=0.5,
                max_tokens=1000,
            )
            msg = resp["message"]
            messages.append(msg)

            if msg.get("tool_calls"):
                for tc in msg["tool_calls"]:
                    func_name = tc["function"]["name"]
                    args = tc["function"]["arguments"]
                    result = self.registry.execute(func_name, **args)
                    messages.append({
                        "role": "tool",
                        "name": func_name,
                        "content": result,
                    })

                final = self.llm.chat(
                    messages=[{"role": "system", "content": system_prompt}, *messages],
                    temperature=0.5,
                    max_tokens=1000,
                )
                msg = final["message"]
                messages.append(msg)

            content = msg.get("content", "").strip()
            if content:
                return content

        return "(completed with no output)"
