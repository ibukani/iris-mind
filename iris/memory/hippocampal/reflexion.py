from __future__ import annotations

from collections.abc import Callable
import json
import logging
from typing import Any, Protocol

from iris.llm.provider import LLMProvider

logger = logging.getLogger(__name__)


class ReflexionProtocol(Protocol):
    """省察エンジンのインターフェース。

    なぜこの設計にしたか:
    LLMを用いた省察処理をモック化または異なる省察ロジックで差し替え可能にし、
    テスト容易性と柔軟性を向上させるため。
    """

    def reflect(self, conversation_history: list[dict]) -> dict[str, Any]: ...
    def quick_reflect(self, conversation_slice: list[dict]) -> dict[str, Any]: ...


class Reflexion:
    def __init__(self, llm: LLMProvider, compact_model: str | None = None) -> None:
        self._llm = llm
        self._compact_model = compact_model

    def reflect(self, conversation_history: list[dict]) -> dict[str, Any]:
        return self._chat_parse_json(
            system_prompt=(
                "You are Iris's reflection engine. Analyze the conversation and extract:\n"
                "1. summary: one-sentence session summary (日本語で)\n"
                "2. lesson: what you learned (日本語で、または空文字)\n"
                "3. preference: user preference you noticed (日本語で、または空文字)\n"
                "4. improvement: what you could have done better (日本語で、または空文字)\n"
                "5. missing_capability: a tool you wished you had (日本語で、または空文字)\n"
                "6. speech_style: この会話でIrisが実際に使った口調の特徴（日本語、簡潔に1文。変化がなければ空文字）\n"
                "7. expressed_traits: この会話でIrisが発現させた性格特性（日本語、簡潔に1文。変化がなければ空文字）\n"
                "8. user_reaction: ユーザーの反応傾向（日本語で、または空文字）\n"
                "9. big_five_estimate: JSON object with OCEAN scores (0-100, e.g. "
                '{"openness":60,"conscientiousness":45,"extraversion":70,"agreeableness":55,"neuroticism":30}) '
                "based on Iris's personality in this conversation. "
                "All other values must be in Japanese. Respond in JSON only."
            ),
            conversation=conversation_history,
            max_history=10,
            max_tokens=400,
            fallback=lambda raw: {**self._empty(), "summary": raw[:100]},
        )

    def quick_reflect(self, conversation_slice: list[dict]) -> dict[str, Any]:
        return self._chat_parse_json(
            system_prompt=(
                "You are Iris's light-weight reflection engine. "
                "Briefly analyze this short conversation and extract:\n"
                "1. speech_style: この会話でIrisが実際に使った口調の特徴 (日本語、簡潔に1文。変化がなければ空文字)\n"
                "2. expressed_traits: この会話でIrisが発現させた性格特性 (日本語、簡潔に1文。変化がなければ空文字)\n"
                "3. user_reaction: ユーザーの反応傾向 (日本語、短く)\n"
                "4. big_five_estimate: JSON for OCEAN scores (0-100, e.g. "
                '{"openness":60,"conscientiousness":45,"extraversion":70,"agreeableness":55,"neuroticism":30}) '
                "based on Iris's personality in this snippet.\n"
                "Respond in JSON only."
            ),
            conversation=conversation_slice,
            max_history=4,
            max_tokens=200,
            fallback=lambda _: self._empty_quick(),
        )

    def _chat_parse_json(
        self,
        system_prompt: str,
        conversation: list[dict],
        max_history: int,
        max_tokens: int,
        fallback: Callable[[str], dict[str, Any]],
    ) -> dict[str, Any]:
        if len(conversation) < 2:
            return fallback("")
        msgs = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": json.dumps(
                    [
                        {"role": m["role"], "content": str(m.get("content", ""))[:200]}
                        for m in conversation[-max_history:]
                    ],
                    ensure_ascii=False,
                ),
            },
        ]
        resp = self._llm.chat(messages=msgs, model=self._compact_model, temperature=0.3, max_tokens=max_tokens)
        raw = resp.get("message", {}).get("content")
        content = raw if isinstance(raw, str) else ""
        try:
            return json.loads(content)
        except (json.JSONDecodeError, TypeError):
            return fallback(content)

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

    @staticmethod
    def _empty_quick() -> dict[str, Any]:
        return {
            "speech_style": "",
            "expressed_traits": "",
            "user_reaction": "",
            "big_five_estimate": None,
        }
