from __future__ import annotations

import logging
from collections.abc import Callable

from iris.agency.execution.interrupt_token import InterruptToken
from iris.agency.execution.tool_executor import ToolExecutionEngine
from iris.kernel.config import ModelConfig
from iris.llm.capability_checker import CapabilityChecker
from iris.llm.llm_bridge import LLMBridge
from iris.memory.manager import MemoryManager
from iris.memory.personality.persona_profile import PersonaProfile
from iris.memory.personality.personality import Personality
from iris.memory.stores import AgentsMdStore

logger = logging.getLogger(__name__)


class LLMPipeline:
    def __init__(
        self,
        llm: LLMBridge,
        model_config: ModelConfig,
        personality: Personality,
        agents_md_store: AgentsMdStore | None = None,
        persona_profile: PersonaProfile | None = None,
        memory: MemoryManager | None = None,
        tool_executor: ToolExecutionEngine | None = None,
        capability_checker: CapabilityChecker | None = None,
        governance_principles: str = "",
    ) -> None:
        self._llm = llm
        self._model_config = model_config
        self._personality = personality
        self._agents_md_store = agents_md_store
        self._persona_profile = persona_profile
        self._memory = memory
        self._tool_executor = tool_executor
        self._capability_checker = capability_checker
        self._governance_principles = governance_principles
        self._session_roles_summary: str = ""
        self._max_tool_iterations: int = 3

    def set_session_roles_summary(self, summary: str) -> None:
        self._session_roles_summary = summary

    def _build_system_prompt(self) -> str:
        agents_md = self._agents_md_store.load() if self._agents_md_store else ""
        speech_style = self._persona_profile.get_speech_style() if self._persona_profile else ""
        traits = self._persona_profile.get_traits() if self._persona_profile else ""
        prefs_list = self._memory.get_user_preferences() if self._memory else []
        user_prefs = "\n".join(f"- {p['content']}" for p in prefs_list) if prefs_list else ""
        governance = self._governance_principles or ""
        session_roles = self._session_roles_summary or "（なし）"

        return self._personality.build_system_prompt(
            agents_md_content=agents_md,
            speech_style=speech_style,
            personality_traits=traits,
            user_preferences=user_prefs,
            governance_principles=governance,
            session_roles=session_roles,
        )

    def _get_tools(self) -> list[dict] | None:
        if self._tool_executor is None:
            return None
        return self._tool_executor.registry.list_tools() or None

    def call(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        on_token: Callable[[str], None] | None = None,
        interrupt_token: InterruptToken | None = None,
    ) -> dict:
        system_prompt = self._build_system_prompt()
        msgs: list[dict] = [{"role": "system", "content": system_prompt}, *messages]

        return self._llm.chat(
            messages=msgs,
            model=self._model_config.get_model("default"),
            temperature=self._model_config.temperature,
            tools=tools,
            on_token=on_token,
            interrupt_token=interrupt_token,
        )

    def generate_proactive(self, context_hint: str = "") -> str:
        system_prompt = self._build_system_prompt()
        tier_prompt = (
            "あなたはIrisです。ユーザーに自然に声をかけてください。\n\n"
            "■ ルール:\n"
            "- 短く（40文字以内）で友好的\n"
            "- ユーザーのことを推測せず、確実にわかることだけ\n"
            "- 質問形式より気遣い・報告形式を優先\n"
            "- 発話内容のみ出力\n\n"
            "■ コンテキスト:\n"
            f"{context_hint}"
        )
        msgs = [
            {"role": "system", "content": system_prompt + "\n\n" + tier_prompt},
            {"role": "user", "content": "短く自然な一言を生成してください。"},
        ]
        try:
            resp = self._llm.chat(
                messages=msgs,
                model=self._model_config.get_model("default"),
                max_tokens=80,
                temperature=0.5,
            )
            text = (resp.get("message", {}) or {}).get("content", "").strip().strip('"')
            if text and len(text) < 120:
                return text
        except Exception as e:
            logger.debug("Proactive speech generation failed: %s", e)
        return "お疲れさまです！何かお手伝いしましょうか？"

    def iterate_with_tools(
        self,
        messages: list[dict],
        on_token: Callable[[str], None] | None = None,
        interrupt_token: InterruptToken | None = None,
    ) -> str:
        tools = self._get_tools()
        if tools and self._capability_checker and not self._capability_checker.supports_tools("default"):
            tools = None

        iteration = 0
        final_text = ""

        while iteration < self._max_tool_iterations:
            if interrupt_token and interrupt_token.is_cancelled:
                logger.debug("LLMPipeline: interrupted during tool iteration")
                break

            iteration += 1
            resp = self.call(messages, tools=tools, on_token=on_token, interrupt_token=interrupt_token)
            msg = resp.get("message", {})

            if msg.get("tool_calls") and self._tool_executor is not None:
                messages.append(msg)
                results = self._tool_executor.execute_all(messages)

                if self._tool_executor.all_side_effects(results):
                    break

                for m in messages[-len(msg["tool_calls"]) :]:
                    if m["role"] == "tool" and len(m.get("content", "")) > 200:
                        m["content"] = m["content"][:200] + "..."
                continue

            final_text = msg.get("content", "")
            if final_text:
                break

        return final_text
