"""
Reflexion — 自己反省エンジン。

会話履歴を LLM に分析させ、教訓・好み・改善点・話し方の特徴を抽出する。
"""

from __future__ import annotations

import json

from iris.llm.provider import LLMProvider


class Reflexion:
    """自己反省エンジン。LLM を使って会話を分析する。"""

    def __init__(self, llm: LLMProvider, compact_model: str | None = None) -> None:
        self.llm = llm
        self.compact_model = compact_model

    def reflect(self, conversation_history: list[dict]) -> dict[str, str]:
        """
        会話全体を分析し、詳細な反省結果を返す。

        Returns:
            dict with keys: summary, lesson, preference, improvement,
            missing_capability, speech_style, expressed_traits, user_reaction
        """
        if len(conversation_history) < 2:
            return self._empty_reflect()

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
                    "Respond in JSON only. All values must be in Japanese."
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
        resp = self.llm.chat(messages=msgs, model=self.compact_model, temperature=0.3, max_tokens=400, keep_alive="0")
        raw = resp["message"].get("content")
        content = raw if isinstance(raw, str) else ""
        try:
            result: dict[str, str] = json.loads(content)
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
            }

    def quick_reflect(self, conversation_slice: list[dict]) -> dict[str, str]:
        """
        短い会話スライスを簡易分析する。

        Returns:
            dict with keys: speech_style, expressed_traits, user_reaction
        """
        if len(conversation_slice) < 2:
            return {"speech_style": "", "expressed_traits": "", "user_reaction": ""}

        msgs = [
            {
                "role": "system",
                "content": (
                    "You are Iris's light-weight reflection engine. "
                    "Briefly analyze this short conversation and extract:\n"
                    "1. speech_style: Irisの口調の特徴 (日本語、短く)\n"
                    "2. expressed_traits: Irisが発現させた性格特性 (日本語、短く)\n"
                    "3. user_reaction: ユーザーの反応傾向 (日本語、短く)\n"
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
        resp = self.llm.chat(messages=msgs, model=self.compact_model, temperature=0.3, max_tokens=200, keep_alive="0")
        raw = resp["message"].get("content")
        content = raw if isinstance(raw, str) else ""
        try:
            result: dict[str, str] = json.loads(content)
            return result
        except (json.JSONDecodeError, TypeError):
            return {"speech_style": "", "expressed_traits": "", "user_reaction": ""}

    @staticmethod
    def should_add_capability(reflection: dict[str, str]) -> bool:
        """反省結果に missing_capability が含まれているか判定する。"""
        return bool(reflection.get("missing_capability"))

    @staticmethod
    def _empty_reflect() -> dict[str, str]:
        return {
            "summary": "",
            "lesson": "",
            "preference": "",
            "improvement": "",
            "missing_capability": "",
            "speech_style": "",
            "expressed_traits": "",
            "user_reaction": "",
        }
