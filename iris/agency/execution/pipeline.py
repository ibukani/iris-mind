from __future__ import annotations

from collections.abc import Callable
import datetime
import logging
from typing import TYPE_CHECKING, Any

from iris.agency.execution.interrupt_token import InterruptToken
from iris.agency.execution.tool_executor import ToolExecutionEngine
from iris.kernel.config import ModelConfig
from iris.llm.capability_checker import CapabilityChecker
from iris.llm.llm_bridge import LLMBridge
from iris.memory.long_term.stores import AgentsMdStore
from iris.memory.manager import MemoryManager
from iris.memory.personality.persona_profile import PersonaProfile
from iris.memory.personality.personality import Personality

if TYPE_CHECKING:
    from iris.kernel.debug_capture import DebugCapture
    from iris.limbic.manager import LimbicManager

logger = logging.getLogger(__name__)

_SITUATION_INSTRUCTIONS: dict[str, str] = {
    "proactive": (
        "## 状況: 自発的な一声\n"
        "時間帯や会話の流れに合わせて、自然に声をかけてください。\n"
        "誰かと会話しているのではなく、自ら会話を始める場面です。"
    ),
}


class LLMPipeline:
    def __init__(
        self,
        llm: LLMBridge,
        model_config: ModelConfig,
        personality: Personality,
        agents_md_store: AgentsMdStore | None = None,
        persona_profile: PersonaProfile | None = None,
        memory: MemoryManager | None = None,
        limbic: LimbicManager | None = None,
        tool_executor: ToolExecutionEngine | None = None,
        capability_checker: CapabilityChecker | None = None,
        governance_principles: str = "",
        debug_capture: DebugCapture | None = None,
    ) -> None:
        self._llm = llm
        self._model_config = model_config
        self._personality = personality
        self._agents_md_store = agents_md_store
        self._persona_profile = persona_profile
        self._memory = memory
        self._limbic = limbic
        self._tool_executor = tool_executor
        self._capability_checker = capability_checker
        self._governance_principles = governance_principles
        self._debug_capture = debug_capture
        self._session_roles_summary: str = ""
        self._max_tool_iterations: int = 3
        self._sysprompt_cache: str | None = None
        self._last_system_prompt: str = ""
        self._last_call_model_role: str = "default"

    def set_session_roles_summary(self, summary: str) -> None:
        self._session_roles_summary = summary

    def _build_system_prompt(self, context_hint: str = "") -> str:
        if self._sysprompt_cache is not None:
            return self._sysprompt_cache

        agents_md = self._agents_md_store.load() if self._agents_md_store else ""
        speech_style = self._persona_profile.get_speech_style() if self._persona_profile else ""
        traits = self._persona_profile.get_traits() if self._persona_profile else ""
        dynamic_personality = self._persona_profile.get_dynamic_personality() if self._persona_profile else ""
        prefs_list = self._memory.get_user_preferences() if self._memory else []
        user_prefs = "\n".join(f"- {p['content']}" for p in prefs_list) if prefs_list else ""
        governance = self._governance_principles or ""
        session_roles = self._session_roles_summary or "（なし）"

        prompt = self._personality.build_system_prompt(
            agents_md_content=agents_md,
            speech_style=speech_style,
            personality_traits=traits,
            user_preferences=user_prefs,
            governance_principles=governance,
            session_roles=session_roles,
        )

        if dynamic_personality:
            prompt += f"\n\n{dynamic_personality}"

        dt_now = datetime.datetime.now()
        weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        weekday = weekdays[dt_now.weekday()]
        current_time_str = f"{dt_now.strftime('%Y-%m-%d %H:%M:%S')} ({weekday})"
        prompt += f"\n\n## 現在日時\n{current_time_str}"

        if self._limbic:
            mood_desc = self._limbic.build_mood_description()
            if mood_desc:
                prompt += f"\n\n## 現在の気分\n{mood_desc}"
            style = self._limbic.build_response_style()
            if style:
                prompt += f"\n\n{style}"

        if context_hint:
            prompt += f"\n\n## 会話コンテキスト\n{context_hint}"
        self._sysprompt_cache = prompt
        return prompt

    def _get_tools(self) -> list[dict[str, Any]] | None:
        if self._tool_executor is None:
            return None
        return self._tool_executor.registry.list_tools() or None

    def call(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        on_token: Callable[[str], None] | None = None,
        interrupt_token: InterruptToken | None = None,
        context_hint: str = "",
        model_role: str = "default",
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        self._sysprompt_cache = None
        system_prompt = self._build_system_prompt(context_hint=context_hint)
        self._last_system_prompt = system_prompt
        self._last_call_model_role = model_role
        msgs: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}, *messages]

        return self._llm.chat(
            messages=msgs,
            model=self._model_config.get_model(model_role),
            temperature=self._model_config.get_effective_temperature(model_role),
            max_tokens=max_tokens or self._model_config.get_effective_max_tokens(model_role),
            tools=tools,
            on_token=on_token,
            interrupt_token=interrupt_token,
        )

    def generate(
        self, plan: dict[str, Any], messages: list[dict[str, Any]], on_token: Callable[[str], None] | None = None
    ) -> str:
        """計画に基づいて、会話メッセージからテキストを生成する（メイン公開メソッド）。

        計画の tools_allowed フラグに基づいて、ツール使用の有無を判定し、
        適切なパイプライン（ツール付き / なし）で生成する。

        Args:
            plan: PlanningManager が生成した計画辞書。
            messages: 会話履歴。role/content のリスト。
            on_token: トークンストリーミングコールバック（オプション）。

        Returns:
            生成されたテキスト。
        """
        self._sysprompt_cache = None
        model_role = plan.get("model_role", "default")
        context_hint = plan.get("context_hint", "")
        max_tokens = plan.get("max_tokens", 0) or None
        if plan.get("tools_allowed", True):
            return self._generate_with_tools(
                messages,
                context_hint=context_hint,
                on_token=on_token,
                model_role=model_role,
                max_tokens=max_tokens,
            )
        temperature = plan.get("temperature", 0.5)
        return self._generate_without_tools(plan, max_tokens, temperature, messages=messages, model_role=model_role)

    def _generate_without_tools(
        self,
        plan: dict[str, Any],
        max_tokens: int | None,
        temperature: float,
        messages: list[dict[str, Any]] | None = None,
        model_role: str = "default",
    ) -> str:
        context_hint = plan.get("context_hint", "")
        system_prompt = self._build_system_prompt(context_hint=context_hint)
        situation = plan.get("situation", "")

        parts = [system_prompt]
        if situation in _SITUATION_INSTRUCTIONS:
            parts.append(_SITUATION_INSTRUCTIONS[situation])

        msgs: list[dict[str, Any]] = [{"role": "system", "content": "\n\n".join(parts)}]

        content = plan.get("content", "")
        if messages and content:
            msgs.extend(messages)

        if content:
            msgs.append({"role": "user", "content": content})
        else:
            msgs.append({"role": "user", "content": "..."})
        text = ""
        try:
            resp = self._llm.chat(
                messages=msgs,
                model=self._model_config.get_model(model_role),
                max_tokens=max_tokens or 80,
                temperature=temperature,
            )
            text = str((resp.get("message", {}) or {}).get("content", "")).strip()
        except Exception as e:
            logger.debug("Short generation failed: %s", e)

        if not text:
            text = "お疲れさまです！何かお手伝いしましょうか？"

        self._capture_debug(
            model_role=model_role,
            system_prompt=system_prompt,
            messages=msgs,
            tools=None,
            response=text,
        )

        return text

    def _generate_with_tools(
        self,
        messages: list[dict],
        on_token: Callable[[str], None] | None = None,
        interrupt_token: InterruptToken | None = None,
        context_hint: str = "",
        model_role: str = "default",
        max_tokens: int | None = None,
    ) -> str:
        tools = self._get_tools()
        if tools and self._capability_checker and not self._capability_checker.supports_tools(model_role):
            tools = None

        iteration = 0
        final_text = ""
        tool_iters: list[dict] = []

        while iteration < self._max_tool_iterations:
            if interrupt_token and interrupt_token.is_cancelled:
                logger.debug("LLMPipeline: interrupted during tool iteration")
                break

            iteration += 1
            resp = self.call(
                messages,
                tools=tools,
                on_token=on_token,
                interrupt_token=interrupt_token,
                context_hint=context_hint,
                model_role=model_role,
                max_tokens=max_tokens,
            )
            msg = resp.get("message", {})

            if msg.get("tool_calls") and self._tool_executor is not None:
                messages.append(msg)
                results = self._tool_executor.execute_all(messages)
                tool_iters.append({"tool_calls": msg["tool_calls"], "results": results})

                if self._tool_executor.all_side_effects(results):
                    break

                for m in messages[-len(msg["tool_calls"]) :]:
                    if m["role"] == "tool" and len(m.get("content", "")) > 200:
                        m["content"] = m["content"][:200] + "..."
                continue

            final_text = msg.get("content", "")
            if final_text:
                break

        sys_prompt = getattr(self, "_last_system_prompt", "")
        self._capture_debug(
            model_role=model_role,
            system_prompt=sys_prompt,
            messages=messages,
            tools=tools,
            response=final_text,
            tool_iterations=tool_iters,
        )

        return final_text

    def _capture_debug(
        self,
        model_role: str,
        system_prompt: str,
        messages: list[dict],
        tools: list[dict] | None,
        response: str,
        tool_iterations: list[dict] | None = None,
    ) -> None:
        """デバッグキャプチャ処理を行い、トークン数をカウントして記録する。"""
        dc = self._debug_capture
        if not (dc and dc.enabled):
            return

        model_name = self._model_config.get_model(model_role)
        history_msgs = [m for m in messages if m.get("role") != "system"]
        tc = {
            "system": dc.count_tokens(system_prompt),
            "history": dc.count_tokens(" ".join(m.get("content", "") or "" for m in history_msgs)),
            "tools": dc.count_tokens(str(tools)) if tools else 0,
            "response": dc.count_tokens(response),
        }
        tc["total"] = sum(tc.values())

        from iris.kernel.debug_capture import CaptureEntry

        dc.capture(
            CaptureEntry(
                id=0,
                timestamp=datetime.datetime.now(),
                model_name=model_name,
                system_prompt=system_prompt,
                messages=history_msgs,
                tools=tools,
                response=response,
                token_counts=tc,
                tool_iterations=tool_iterations or [],
            )
        )
