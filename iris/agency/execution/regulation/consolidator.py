from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import TYPE_CHECKING

from langchain_core.messages import BaseMessage, SystemMessage

if TYPE_CHECKING:
    from iris.kernel.config import ModelConfig
    from iris.llm.context import LLMContextWindowManager

from loguru import logger


class Consolidator:
    def __init__(
        self,
        messages_getter: Callable[[], list[BaseMessage]],
        context_window_mgr: LLMContextWindowManager | None = None,
        model_config: ModelConfig | None = None,
        context_window: int = 0,
    ) -> None:
        self._get_messages = messages_getter
        self._context_window_mgr = context_window_mgr
        self._model_config = model_config
        self._context_window = context_window

    async def run_compression(self) -> None:
        messages = self._get_messages()
        try:
            if self._context_window_mgr:
                await self._compact_messages(messages)
        except Exception:
            logger.exception("Compression failed")

    async def _compact_messages(self, messages: list[BaseMessage]) -> None:
        cwm = self._context_window_mgr
        if cwm is None:
            return
        model_name = self._model_config.get_model("medium") if self._model_config else None
        effective_ctx = (
            self._model_config.get_effective_context_window("medium") if self._model_config else self._context_window
        )
        summary = await cwm.check_and_summarize(
            messages,
            effective_ctx,
            model_name=model_name,
        )
        if not summary or len(messages) <= 6:
            return
        keep = 6
        messages[:] = [
            SystemMessage(content=f"## Session Summary\n{summary}"),
            *messages[-keep:],
        ]
        logger.info("Auto-compacted: summary_len={}, kept={}", len(summary), keep)

    def compact_context(self) -> str:
        if self._context_window_mgr is None:
            return "Context manager not available"
        messages = self._get_messages()
        if len(messages) < 2:
            return "Not enough messages to compact"
        summary = asyncio.run(self._context_window_mgr.compact(messages))
        keep = 6
        messages[:] = [SystemMessage(content=f"## Session Summary\n{summary}"), *messages[-keep:]]
        return f"Compacted: {len(summary)} chars summary, kept last {keep} messages"
