from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from iris.llm.bridge import LLMBridge

from langchain_core.messages import HumanMessage, SystemMessage
from loguru import logger


class QuestionGenerator:
    def __init__(self, llm: LLMBridge | None = None) -> None:
        self._llm = llm

    def generate(self, topic: str) -> str:
        if self._llm is None:
            return f"{topic}についての自発的調査"

        system_prompt = (
            "You are Iris's curiosity generator. Given a general interest topic, "
            "generate one specific, deep, and concrete scientific or philosophical question in Japanese "
            "that Iris would want to investigate. Do not output anything other than the question itself."
        )
        user_content = f"興味トピック: {topic}"
        msgs = [SystemMessage(content=system_prompt), HumanMessage(content=user_content)]

        try:
            resp = asyncio.run(self._llm.chat(messages=msgs, model=None, temperature=0.7, max_tokens=150))
            raw = str(resp.content)
            if raw.strip():
                return raw.strip()
        except Exception as e:
            logger.error("Failed to generate question from topic: %s", e)
        return f"{topic}についての自発的調査"
