from __future__ import annotations

import json
import logging
from typing import Any

from iris.llm.provider import LLMProvider

logger = logging.getLogger(__name__)


class Reflexion:
    def __init__(self, llm: LLMProvider, compact_model: str | None = None) -> None:
        self._llm = llm
        self._compact_model = compact_model

    def reflect(self, conversation_history: list[dict]) -> dict[str, Any]:
        if len(conversation_history) < 2:
            return self._empty()

        msgs = [
            {
                "role": "system",
                "content": (
                    "You are Iris's reflection engine. Analyze the conversation and extract:\n"
                    "1. summary: one-sentence session summary (日本語で)\n"
                    "2. lesson: what you learned (日本語で、または空文字)\n"
                    "3. preference: user preference you noticed (日本語で、または空文字)\n"
                    "4. improvement: what you could have done better (日本語で、または空文字)\n"
                    "5. missing_capability: a tool you wished you had (日本語で、または空文字)\n"
                    "6. speech_style: Irisの口調・話し方の特徴（日本語で、または空文字）\n"
                    "7. expressed_traits: Irisがこの会話で発現させた性格特性（日本語で、または空文字）\n"
                    "8. user_reaction: ユーザーの反応傾向（日本語で、または空文字）\n"
                    "9. big_five_estimate: JSON object with OCEAN scores (0-100, e.g. "
                    '{"openness":60,"conscientiousness":45,"extraversion":70,"agreeableness":55,"neuroticism":30}) '
                    "based on Iris's personality in this conversation. "
                    "All other values must be in Japanese."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    [
                        {
                            "role": m["role"],
                            "content": str(m.get("content", ""))[:200],
                        }
                        for m in conversation_history[-10:]
                    ],
                    ensure_ascii=False,
                ),
            },
        ]
        resp = self._llm.chat(messages=msgs, model=self._compact_model, temperature=0.3, max_tokens=400)
        raw = resp.get("message", {}).get("content")
        content = raw if isinstance(raw, str) else ""
        try:
            result: dict[str, Any] = json.loads(content)
            return result
        except (json.JSONDecodeError, TypeError):
            return {
                "summary": content[:100],
                "lesson": "",
                "preference": "",
                "improvement": "",
                "missing_capability": "",
                "speech_style": "",
                "expressed_traits": "",
                "user_reaction": "",
                "big_five_estimate": None,
            }

    def quick_reflect(self, conversation_slice: list[dict]) -> dict[str, Any]:
        if len(conversation_slice) < 2:
            return {"speech_style": "", "expressed_traits": "", "user_reaction": "", "big_five_estimate": None}

        msgs = [
            {
                "role": "system",
                "content": (
                    "You are Iris's light-weight reflection engine. "
                    "Briefly analyze this short conversation and extract:\n"
                    "1. speech_style: Irisの口調の特徴 (日本語、短く)\n"
                    "2. expressed_traits: Irisが発現させた性格特性 (日本語、短く)\n"
                    "3. user_reaction: ユーザーの反応傾向 (日本語、短く)\n"
                    "4. big_five_estimate: JSON for OCEAN scores (0-100, e.g. "
                    '{"openness":60,"conscientiousness":45,"extraversion":70,"agreeableness":55,"neuroticism":30}) '
                    "based on Iris's personality in this snippet.\n"
                    "Respond in JSON only."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    [
                        {
                            "role": m["role"],
                            "content": str(m.get("content", ""))[:200],
                        }
                        for m in conversation_slice[-4:]
                    ],
                    ensure_ascii=False,
                ),
            },
        ]
        resp = self._llm.chat(messages=msgs, model=self._compact_model, temperature=0.3, max_tokens=200)
        raw = resp.get("message", {}).get("content")
        content = raw if isinstance(raw, str) else ""
        try:
            result: dict[str, Any] = json.loads(content)
            return result
        except (json.JSONDecodeError, TypeError):
            return {"speech_style": "", "expressed_traits": "", "user_reaction": "", "big_five_estimate": None}

    @staticmethod
    def should_add_capability(reflection: dict[str, str | None]) -> bool:
        return bool(reflection.get("missing_capability"))

    @staticmethod
    def _empty() -> dict[str, Any]:
        return {
            "summary": "",
            "lesson": "",
            "preference": "",
            "improvement": "",
            "missing_capability": "",
            "speech_style": "",
            "expressed_traits": "",
            "user_reaction": "",
            "big_five_estimate": None,
        }
