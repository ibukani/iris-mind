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
            return {"summary": "", "lesson": "", "preference": "", "improvement": "", "missing_capability": "",
                    "speech_style": "", "expressed_traits": "", "user_reaction": ""}

        msgs = [
            {"role": "system", "content": (
                "You are Iris's reflection engine. Analyze the conversation and extract:\n"
                "1. summary: one-sentence session summary (日本語で)\n"
                "2. lesson: what you learned (日本語で、または空文字)\n"
                "3. preference: user preference you noticed (日本語で、または空文字)\n"
                "4. improvement: what you could have done better (日本語で、または空文字)\n"
                "5. missing_capability: a tool you wished you had (日本語で、または空文字)\n"
                "6. speech_style: Irisの口調・話し方の特徴（例：丁寧だが親しみやすい、簡潔で要点重視）(日本語で、または空文字)\n"
                "7. expressed_traits: Irisがこの会話で発現させた性格特性（例：慎重、好奇心旺盛、皮肉）(日本語で、または空文字)\n"
                "8. user_reaction: ユーザーの反応傾向、好みそうなスタイル（例：簡潔な回答を好む、冗談が通じる）(日本語で、または空文字)\n"
                "Respond in JSON only. All values must be in Japanese."
            )},
            {"role": "user", "content": json.dumps(
                [{"role": m["role"], "content": str(m.get("content", ""))[:200]}
                 for m in conversation_history[-10:]], ensure_ascii=False
            )},
        ]
        resp = self.llm.chat(messages=msgs, temperature=0.3, max_tokens=400)
        content = resp["message"].get("content", "")
        try:
            return json.loads(content)
        except (json.JSONDecodeError, TypeError):
            return {"summary": content[:100], "lesson": "", "preference": "", "improvement": "",
                    "missing_capability": "", "speech_style": "", "expressed_traits": "", "user_reaction": ""}

    def quick_reflect(self, conversation_slice: list[dict]) -> dict:
        if len(conversation_slice) < 2:
            return {"speech_style": "", "expressed_traits": "", "user_reaction": ""}
        msgs = [
            {"role": "system", "content": (
                "You are Iris's light-weight reflection engine. Briefly analyze this short conversation and extract:\n"
                "1. speech_style: Irisの口調の特徴 (日本語、短く)\n"
                "2. expressed_traits: Irisが発現させた性格特性 (日本語、短く)\n"
                "3. user_reaction: ユーザーの反応傾向 (日本語、短く)\n"
                "Respond in JSON only."
            )},
            {"role": "user", "content": json.dumps(
                [{"role": m["role"], "content": str(m.get("content", ""))[:200]}
                 for m in conversation_slice[-4:]], ensure_ascii=False
            )},
        ]
        resp = self.llm.chat(messages=msgs, temperature=0.3, max_tokens=200)
        content = resp["message"].get("content", "")
        try:
            return json.loads(content)
        except (json.JSONDecodeError, TypeError):
            return {"speech_style": "", "expressed_traits": "", "user_reaction": ""}

    def should_add_capability(self, reflection: dict) -> bool:
        return bool(reflection.get("missing_capability"))
