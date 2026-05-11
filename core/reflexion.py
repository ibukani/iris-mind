from __future__ import annotations
import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.llm_bridge import LLMBridge


class Reflexion:
    def __init__(self, llm: LLMBridge):
        self.llm = llm

    def reflect(self, conversation_history: list[dict]) -> dict:
        if len(conversation_history) < 2:
            return {"summary": "", "lesson": "", "preference": "", "improvement": "", "missing_capability": ""}

        msgs = [
            {"role": "system", "content": (
                "You are Iris's reflection engine. Analyze the conversation and extract:\n"
                "1. summary: one-sentence session summary\n"
                "2. lesson: what you learned (or empty)\n"
                "3. preference: user preference you noticed (or empty)\n"
                "4. improvement: what you could have done better (or empty)\n"
                "5. missing_capability: a tool you wished you had (or empty)\n"
                "Respond in JSON only."
            )},
            {"role": "user", "content": json.dumps(
                [{"role": m["role"], "content": str(m.get("content", ""))[:200]}
                 for m in conversation_history[-10:]], ensure_ascii=False
            )},
        ]
        resp = self.llm.chat(messages=msgs, temperature=0.3, max_tokens=300)
        content = resp["message"].get("content", "")
        try:
            return json.loads(content)
        except (json.JSONDecodeError, TypeError):
            return {"summary": content[:100], "lesson": "", "preference": "", "improvement": "", "missing_capability": ""}

    def should_add_capability(self, reflection: dict) -> bool:
        return bool(reflection.get("missing_capability"))
