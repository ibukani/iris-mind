"""
ConversationService — 会話処理パイプライン。

UserInputEvent を購読し、LLM 応答を生成 → AgentResponseEvent を発行する。
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from .config import Config
from .event_bus import AgentResponseEvent, EventBus, UserInputEvent
from .memory_manager import MemoryManager

logger = logging.getLogger(__name__)


class ConversationService:
    """
    会話処理サービス。

    EventBus 経由で UserInputEvent を購読し、以下のフローを実行する：
    1. Personality でシステムプロンプト構築
    2. LLM 呼び出し
    3. AgentResponseEvent 発行
    """

    def __init__(
        self,
        event_bus: EventBus,
        memory: MemoryManager,
        llm: Any,
        personality: Any,
        config: Config,
    ) -> None:
        self._event_bus = event_bus
        self._memory = memory
        self._llm = llm
        self._personality = personality
        self._model_config = config.model
        self._messages: list[dict] = []

        self._event_bus.subscribe("UserInputEvent", self._on_user_input)

    # ── イベントハンドラ ──────────────────────────────────

    def _on_user_input(self, event: UserInputEvent) -> None:
        """ユーザー入力イベントを処理する。"""
        self._messages.append({"role": "user", "content": event.content})

        try:
            response_text = self._call_llm()
        except Exception as e:
            response_text = f"[Error: {e}]"
            logger.exception("LLM call failed")

        self._messages.append({"role": "assistant", "content": response_text})

        self._event_bus.publish(
            AgentResponseEvent(
                timestamp=datetime.now(),
                source="assistant",
                content=response_text,
            )
        )

    # ── LLM 呼び出し ─────────────────────────────────────

    def _call_llm(self) -> str:
        """LLM を呼び出し応答テキストを取得する。"""
        system_prompt = self._personality.build_system_prompt()
        messages = [{"role": "system", "content": system_prompt}, *self._messages]

        resp = self._llm.chat(
            messages=messages,
            model=self._model_config.base_model,
            temperature=self._model_config.temperature,
        )
        return resp.get("message", {}).get("content", "")

    # ── 会話履歴管理 ─────────────────────────────────────

    def clear_history(self) -> None:
        """会話履歴をクリアする。"""
        self._messages.clear()
        logger.info("Conversation history cleared")
