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
from .context import ContextManager
from .event_bus import AgentResponseEvent, EventBus, UserInputEvent
from .memory_manager import MemoryManager
from .proactive import SELF_GOVERNANCE_PRINCIPLES
from .tool_executor import ToolExecutionEngine

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
        tool_executor: ToolExecutionEngine | None = None,
        context_manager: ContextManager | None = None,
        persona_profile: Any | None = None,
        agents_md_store: Any | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._memory = memory
        self._llm = llm
        self._personality = personality
        self._model_config = config.model
        self._reflexion = reflexion
        self._reflect_interval = reflect_interval
        self._tool_executor = tool_executor
        self._context_manager = context_manager
        self._persona_profile = persona_profile
        self._agents_md_store = agents_md_store
        self._context_window = config.model.context_window
        self._max_tool_iterations: int = 3
        self._messages: list[dict] = []
        self._msg_count_since_reflect: int = 0

        self._event_bus.subscribe("UserInputEvent", self._on_user_input)

    # ── イベントハンドラ ──────────────────────────────────

    def _on_user_input(self, event: UserInputEvent) -> None:
        """ユーザー入力イベントを処理する。"""
        self._messages.append({"role": "user", "content": event.content})

        try:
            response_text = self._call_llm_with_tools()
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
        self._maybe_compact()

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
            if self._persona_profile is not None:
                self._persona_profile.update_from_reflection(result)
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
                    _kind="system",
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

    def _maybe_compact(self) -> None:
        """トークン数が閾値を超えた場合、会話履歴を要約する。"""
        if self._context_manager is None or self._context_window <= 0:
            return
        self._context_manager.check_and_summarize(
            self._messages,
            context_window=self._context_window,
        )

    def _call_llm(self, tools: list[dict] | None = None) -> dict:
        """LLM を呼び出し応答を返す。"""
        agents_md = self._agents_md_store.load() if self._agents_md_store else ""
        speech_style = self._persona_profile.get_speech_style() if self._persona_profile else ""
        traits = self._persona_profile.get_traits() if self._persona_profile else ""
        prefs_list = self._memory.get_user_preferences()
        user_prefs = "\n".join(f"- {p['content']}" for p in prefs_list) if prefs_list else ""
        governance = "\n".join(f"- {p}" for p in SELF_GOVERNANCE_PRINCIPLES) if SELF_GOVERNANCE_PRINCIPLES else ""

        system_prompt = self._personality.build_system_prompt(
            agents_md_content=agents_md,
            speech_style=speech_style,
            personality_traits=traits,
            user_preferences=user_prefs,
            governance_principles=governance,
        )

        ctx_mgr = self._context_manager
        if ctx_mgr is not None and ctx_mgr.has_summary:
            messages = [{"role": "system", "content": system_prompt}]
            messages += ctx_mgr.build_compact_messages(self._messages)
        else:
            messages = [{"role": "system", "content": system_prompt}, *self._messages]

        return self._llm.chat(
            messages=messages,
            model=self._model_config.get_model("default"),
            temperature=self._model_config.temperature,
            tools=tools,
        )

    def _call_llm_with_tools(self) -> str:
        """
        Tool Call 対応の LLM 呼び出し。

        1. 利用可能なツール定義を LLM に渡す
        2. LLM が tool_calls を返したら ToolExecutionEngine で実行
        3. 結果を追跡し、必要に応じて再度 LLM を呼び出す
        4. 最終的なテキスト応答を返す
        """
        tools = self._get_tools()
        iteration = 0
        final_text = ""

        while iteration < self._max_tool_iterations:
            iteration += 1
            resp = self._call_llm(tools=tools)
            msg = resp.get("message", {})

            if msg.get("tool_calls") and self._tool_executor is not None:
                self._messages.append(msg)
                self._tool_executor.execute_all(self._messages)
                for m in self._messages[-len(msg["tool_calls"]) :]:
                    if m["role"] == "tool" and len(m.get("content", "")) > 200:
                        m["content"] = m["content"][:200] + "..."
                continue

            final_text = msg.get("content", "")
            if final_text:
                break

        return final_text

    def _get_tools(self) -> list[dict] | None:
        """利用可能なツール定義を取得する。"""
        if self._tool_executor is None:
            return None
        return self._tool_executor.registry.list_tools() or None

    # ── 会話履歴管理 ─────────────────────────────────────

    def clear_history(self) -> None:
        """会話履歴をクリアする。"""
        self._messages.clear()
        self._msg_count_since_reflect = 0
        if self._context_manager is not None:
            self._context_manager.clear()
        logger.info("Conversation history cleared")
