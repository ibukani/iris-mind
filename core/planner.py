from __future__ import annotations
import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.llm_bridge import LLMBridge


class Planner:
    """タスク分解エンジン。複雑な要求をサブタスクに分割。"""

    PLAN_SYSTEM_PROMPT = (
        "You are a task planner. Analyze the user's request and determine if it needs "
        "to be broken into subtasks. Reply in JSON only:\n"
        "- For simple tasks: {\"mode\": \"simple\"}\n"
        "- For complex tasks: {\"mode\": \"complex\", \"reason\": \"...\", "
        "\"subtasks\": [{\"name\": \"...\", \"description\": \"...\"}]}\n"
        "A task is complex when it requires 2+ distinct steps like research then write, "
        "or multiple tool calls in sequence. Be concise."
    )

    def __init__(self, llm: LLMBridge):
        self.llm = llm

    def analyze(self, user_input: str, context: str = "") -> dict:
        resp = self.llm.chat(
            messages=[
                {"role": "system", "content": self.PLAN_SYSTEM_PROMPT},
                {"role": "user", "content": f"Context: {context}\n\nRequest: {user_input}"},
            ],
            temperature=0.3,
            max_tokens=500,
        )
        content = resp["message"].get("content", "")
        try:
            return json.loads(content)
        except (json.JSONDecodeError, TypeError):
            return {"mode": "simple"}

    def is_complex(self, plan: dict) -> bool:
        return plan.get("mode") == "complex" and len(plan.get("subtasks", [])) > 0
