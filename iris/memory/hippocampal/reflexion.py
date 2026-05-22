from __future__ import annotations

from collections.abc import Callable
import json
from typing import Any, Protocol

from loguru import logger
from pydantic import BaseModel, Field

from iris.llm.protocol import LLMProvider


class QuickReflexionResult(BaseModel):
    speech_style: str = Field(default="", description="この会話でIrisが実際に使った口調の特徴（日本語、簡潔に1文）")
    expressed_traits: str = Field(default="", description="この会話でIrisが発現させた性格特性（日本語、簡潔に1文）")
    user_reaction: str = Field(default="", description="ユーザーの反応傾向（日本語、短く）")
    big_five_estimate: dict[str, int] | None = Field(default=None, description="JSON object with OCEAN scores (0-100)")


class ReflexionResult(QuickReflexionResult):
    summary: str = Field(description="one-sentence session summary (日本語で)")
    lesson: str = Field(default="", description="what you learned (日本語で、または空文字)")
    preference: str = Field(default="", description="user preference you noticed (日本語で、または空文字)")
    improvement: str = Field(default="", description="what you could have done better (日本語で、または空文字)")
    missing_capability: str = Field(default="", description="a tool you wished you had (日本語で、または空文字)")
    new_goals: list[str] = Field(
        default_factory=list,
        description="新たに発見した中長期的な目標や、達成すべきタスクのリスト（日本語で）。特になければ空リスト。",
    )
    new_interests: list[str] = Field(
        default_factory=list,
        description="対話や文脈から、Iris自身がもっと詳しく知りたい・探求したいと内発的に思ったこと、興味を持った学術的・哲学的・技術的トピック（日本語で）。特になければ空リスト。",
    )


class ProactiveEvaluationResult(BaseModel):
    satisfaction: float = Field(
        description="今回の調査結果に対する自己納得度（0.0〜1.0）。疑問や興味がどれだけ解消・満足されたか。"
    )
    summary: str = Field(description="調査結果の簡単なまとめ（日本語、1文）")
    next_interests: list[str] = Field(
        default_factory=list,
        description="今回の調査結果を受けて、さらに新しく生じた興味や、次に調べたい関連トピック（日本語で）。",
    )


class ReflexionProtocol(Protocol):
    """省察エンジンのインターフェース。

    なぜこの設計にしたか:
    LLMを用いた省察処理をモック化または異なる省察ロジックで差し替え可能にし、
    テスト容易性と柔軟性を向上させるため。
    """

    def reflect(self, conversation_history: list[dict]) -> dict[str, Any]: ...
    def quick_reflect(self, conversation_slice: list[dict]) -> dict[str, Any]: ...
    def evaluate_proactive_result(self, topic: str, content: str) -> dict[str, Any]: ...


class Reflexion:
    def __init__(self, llm: LLMProvider, compact_model: str | None = None) -> None:
        self._llm = llm
        self._compact_model = compact_model

    def evaluate_proactive_result(self, topic: str, content: str) -> dict[str, Any]:
        schema_json = json.dumps(ProactiveEvaluationResult.model_json_schema(), ensure_ascii=False)
        system_prompt = (
            "You are Iris's self-reflection engine evaluating a proactive investigation.\n"
            f"You must strictly output a valid JSON object matching this schema:\n{schema_json}\n"
            "All string values must be in Japanese. Respond in JSON only."
        )
        user_content = f"調査したトピック: {topic}\n\n調査によって得られた内容:\n{content}"
        msgs = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_content}]
        import asyncio

        resp = asyncio.run(self._llm.chat(messages=msgs, model=self._compact_model, temperature=0.3, max_tokens=400))
        raw = resp.get("message", {}).get("content")
        content_str = raw if isinstance(raw, str) else ""
        try:
            result = json.loads(content_str)
            if isinstance(result, dict):
                return dict(ProactiveEvaluationResult.model_validate(result).model_dump())
        except Exception as e:
            logger.error("Proactive evaluation validation failed: %s", e)
        return {"satisfaction": 0.0, "summary": "調査結果の評価に失敗しました。", "next_interests": []}

    def reflect(self, conversation_history: list[dict]) -> dict[str, Any]:
        schema_json = json.dumps(ReflexionResult.model_json_schema(), ensure_ascii=False)
        system_prompt = (
            "You are Iris's reflection engine. Analyze the conversation and extract the required fields.\n"
            f"You must strictly output a valid JSON object matching this schema:\n{schema_json}\n"
            "All string values must be in Japanese. Respond in JSON only."
        )

        raw_dict = self._chat_parse_json(
            system_prompt=system_prompt,
            conversation=conversation_history,
            max_history=10,
            max_tokens=600,
            fallback=lambda raw: {**self._empty(), "summary": raw[:100]},
        )
        try:
            return dict(ReflexionResult.model_validate(raw_dict).model_dump())
        except Exception as e:
            logger.error("Reflexion validation failed: %s", e)
            return self._empty()

    def quick_reflect(self, conversation_slice: list[dict]) -> dict[str, Any]:
        schema_json = json.dumps(QuickReflexionResult.model_json_schema(), ensure_ascii=False)
        system_prompt = (
            "You are Iris's light-weight reflection engine. Briefly analyze this short conversation.\n"
            f"You must strictly output a valid JSON object matching this schema:\n{schema_json}\n"
            "Respond in JSON only."
        )
        raw_dict = self._chat_parse_json(
            system_prompt=system_prompt,
            conversation=conversation_slice,
            max_history=4,
            max_tokens=300,
            fallback=lambda _: self._empty_quick(),
        )
        try:
            return dict(QuickReflexionResult.model_validate(raw_dict).model_dump())
        except Exception as e:
            logger.error("Quick Reflexion validation failed: %s", e)
            return self._empty_quick()

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
        import asyncio

        resp = asyncio.run(
            self._llm.chat(messages=msgs, model=self._compact_model, temperature=0.3, max_tokens=max_tokens)
        )
        raw = resp.get("message", {}).get("content")
        content = raw if isinstance(raw, str) else ""
        try:
            result = json.loads(content)
            if isinstance(result, dict):
                return result
            return fallback(content)
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
            "new_goals": [],
            "new_interests": [],
        }

    @staticmethod
    def _empty_quick() -> dict[str, Any]:
        return {
            "speech_style": "",
            "expressed_traits": "",
            "user_reaction": "",
            "big_five_estimate": None,
        }
