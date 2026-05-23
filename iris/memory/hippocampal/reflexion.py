from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from loguru import logger
import orjson
from pydantic import BaseModel, Field

from iris.llm.bridge import LLMBridge


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

    async def reflect(self, conversation_history: list[BaseMessage]) -> dict[str, Any]: ...
    async def quick_reflect(self, conversation_slice: list[BaseMessage]) -> dict[str, Any]: ...
    async def evaluate_proactive_result(self, topic: str, content: str) -> dict[str, Any]: ...


class Reflexion:
    def __init__(self, llm: LLMBridge, compact_model: str | None = None) -> None:
        self._llm = llm
        self._compact_model = compact_model

    async def evaluate_proactive_result(self, topic: str, content: str) -> dict[str, Any]:
        system_prompt = (
            "You are Iris's self-reflection engine evaluating a proactive investigation.\n"
            "All string values must be in Japanese."
        )
        user_content = f"調査したトピック: {topic}\n\n調査によって得られた内容:\n{content}"
        msgs: list[BaseMessage] = [SystemMessage(content=system_prompt), HumanMessage(content=user_content)]

        try:
            result = await self._llm.chat_with_structured_output(
                schema=ProactiveEvaluationResult,
                messages=msgs,
                model=self._compact_model,
                temperature=0.3,
                max_tokens=400,
            )
            if result:
                return dict(result.model_dump())
        except Exception as e:
            logger.error("Proactive evaluation validation failed: {}", e)
        return {"satisfaction": 0.0, "summary": "調査結果の評価に失敗しました。", "next_interests": []}

    async def reflect(self, conversation_history: list[BaseMessage]) -> dict[str, Any]:
        system_prompt = (
            "You are Iris's reflection engine. Analyze the conversation and extract the required fields.\n"
            "All string values must be in Japanese."
        )

        return await self._chat_structured(
            schema=ReflexionResult,
            system_prompt=system_prompt,
            conversation=conversation_history,
            max_history=10,
            max_tokens=600,
            fallback=lambda: self._empty(),
        )

    async def quick_reflect(self, conversation_slice: list[BaseMessage]) -> dict[str, Any]:
        system_prompt = "You are Iris's light-weight reflection engine. Briefly analyze this short conversation.\n"
        return await self._chat_structured(
            schema=QuickReflexionResult,
            system_prompt=system_prompt,
            conversation=conversation_slice,
            max_history=4,
            max_tokens=300,
            fallback=lambda: self._empty_quick(),
        )

    async def _chat_structured(
        self,
        schema: Any,
        system_prompt: str,
        conversation: list[BaseMessage],
        max_history: int,
        max_tokens: int,
        fallback: Callable[[], dict[str, Any]],
    ) -> dict[str, Any]:
        if len(conversation) < 2:
            return fallback()

        conv_text_list = []
        for m in conversation[-max_history:]:
            role = m.type
            content = str(m.content)[:200]
            conv_text_list.append({"role": role, "content": content})

        msgs: list[BaseMessage] = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=orjson.dumps(conv_text_list).decode("utf-8")),
        ]

        try:
            result = await self._llm.chat_with_structured_output(
                schema=schema,
                messages=msgs,
                model=self._compact_model,
                temperature=0.3,
                max_tokens=max_tokens,
            )
            if result:
                return dict(result.model_dump())
            return fallback()
        except Exception as e:
            logger.error("Structured chat validation failed: {}", e)
            return fallback()

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
