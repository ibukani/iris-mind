"""
ConversationService — 会話処理パイプライン。

UserInputEvent を購読し、LLM 応答を生成 → AgentResponseEvent を発行する。
一定ターン数ごとに Reflexion による自己反省を実行し、結果を SemanticStore に保存する。
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
    4. Nターンごとに Reflexion.quick_reflect → SemanticStore 保存
    """

    def __init__(
        self,
        event_bus: EventBus,
        memory: MemoryManager,
        llm: Any,
        personality: Any,
        config: Config,
        reflexion: Any | None = None,
        reflect_interval: int = 3,
    ) -> None:
        self._event_bus = event_bus
        self._memory = memory
        self._llm = llm
        self._personality = personality
        self._model_config = config.model
        self._reflexion = reflexion
        self._reflect_interval = reflect_interval
        self._messages: list[dict] = []
        self._msg_count_since_reflect: int = 0

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

        self._msg_count_since_reflect += 1
        self._maybe_quick_reflect()

    # ── Reflexion ────────────────────────────────────────

    def _maybe_quick_reflect(self) -> None:
        """Nターンごとに quick_reflect を実行し結果を SemanticStore に保存する。"""
        if self._reflexion is None:
            return
        if self._msg_count_since_reflect < self._reflect_interval:
            return
        if len(self._messages) < 2:
            return

        self._msg_count_since_reflect = 0
        try:
            result = self._reflexion.quick_reflect(self._messages)

            if result.get("speech_style"):
                self._memory.add_semantic_by_type(
                    entry_type="trait",
                    content=f"Irisの話し方: {result['speech_style']}",
                    tags=["speech_style"],
                )
            if result.get("expressed_traits"):
                self._memory.add_semantic_by_type(
                    entry_type="trait",
                    content=f"Irisの性格特性: {result['expressed_traits']}",
                    tags=["personality_trait"],
                )
            if result.get("user_reaction"):
                self._memory.add_semantic_by_type(
                    entry_type="preference",
                    content=f"ユーザーの反応傾向: {result['user_reaction']}",
                    tags=["user_reaction"],
                )
            logger.info(
                "Quick reflect stored: speech_style=%s traits=%s reaction=%s",
                bool(result.get("speech_style")),
                bool(result.get("expressed_traits")),
                bool(result.get("user_reaction")),
            )
        except Exception as e:
            logger.exception("Quick reflect failed: %s", e)

    def session_reflect(self) -> None:
        """セッション終了時に full reflect を実行する。"""
        if self._reflexion is None:
            return
        if len(self._messages) < 2:
            return

        try:
            result = self._reflexion.reflect(self._messages)
            if result.get("summary"):
                self._memory.add_episodic(
                    content=f"[session summary] {result['summary']}",
                    kind="system",
                )
            for key, entry_type in [
                ("lesson", "lesson"),
                ("preference", "preference"),
                ("improvement", "lesson"),
            ]:
                val = result.get(key, "")
                if val:
                    self._memory.add_semantic_by_type(
                        entry_type=entry_type,
                        content=val,
                    )
            logger.info("Session reflect completed")
        except Exception as e:
            logger.exception("Session reflect failed: %s", e)

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
        self._msg_count_since_reflect = 0
        logger.info("Conversation history cleared")
