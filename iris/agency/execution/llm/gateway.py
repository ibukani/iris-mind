from __future__ import annotations

from collections.abc import Callable
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from iris.agency.execution.llm.prompt_builder import SystemPromptBuilder
from iris.agency.modulation import ModulationState
from iris.kernel.config import ModelConfig
from iris.kernel.debug_capture import DebugCapture
from iris.llm.bridge import LLMBridge
from iris.llm.capability import CapabilityChecker
from iris.llm.interrupt_token import InterruptToken
from iris.llm.prompt import Personality
from iris.memory.long_term.stores import AgentsMdStore
from iris.memory.manager import MemoryManager


class LLMGateway:
    def __init__(
        self,
        llm: LLMBridge,
        model_config: ModelConfig,
        personality: Personality,
        agents_md_store: AgentsMdStore | None = None,
        persona_profile: Any | None = None,
        memory: MemoryManager | None = None,
        capability_checker: CapabilityChecker | None = None,
        debug_capture: DebugCapture | None = None,
        prompts_dir: str | None = None,
    ) -> None:
        self._llm = llm
        self._model_config = model_config
        self._personality = personality
        self._capability_checker = capability_checker
        self._debug_capture = debug_capture
        self._session_roles_summary: str = ""
        self._current_user_identity: str = ""
        self._last_system_prompt: str = ""
        self._last_call_model_role: str = "medium"

        self._prompt_builder = SystemPromptBuilder(
            personality=personality,
            agents_md_store=agents_md_store,
            persona_profile=persona_profile,
            memory=memory,
            prompts_dir=prompts_dir,
        )

    def set_session_roles_summary(self, summary: str) -> None:
        self._session_roles_summary = summary

    def set_current_user_identity(self, identity: str) -> None:
        self._current_user_identity = identity

    def build_system_messages(
        self,
        context_hint: str,
        response_style: str = "",
        node_type: str = "general_task",
        include_profile: bool = True,
        chaos_level: float = 0.0,
    ) -> list[BaseMessage]:
        return self._prompt_builder.build(
            node_type=node_type,
            context_hint=context_hint,
            response_style=response_style,
            session_roles_summary=self._session_roles_summary,
            current_user_identity=self._current_user_identity,
            include_profile=include_profile,
            chaos_level=chaos_level,
        )

    async def _call_llm(
        self,
        system_msgs: list[BaseMessage],
        messages: list[BaseMessage],
        model_role: str,
        max_tokens: int | None,
        temperature: float | None = None,
        tools: list[dict[str, Any]] | None = None,
        on_token: Callable[[str], None] | None = None,
        interrupt_token: InterruptToken | None = None,
        priority: int = 0,
        enable_thinking: bool = False,
    ) -> AIMessage:
        msgs: list[BaseMessage] = [*system_msgs, *messages]
        self._last_system_prompt = "\n\n".join(str(m.content) for m in system_msgs) if system_msgs else ""
        self._last_call_model_role = model_role

        resp = await self._llm.chat(
            messages=msgs,
            model=self._model_config.get_model(model_role),
            temperature=temperature or self._model_config.get_effective_temperature(model_role),
            max_tokens=max_tokens or self._model_config.get_effective_max_tokens(model_role),
            tools=tools,
            on_token=on_token,
            interrupt_token=interrupt_token,
            priority=priority,
            reasoning=enable_thinking or None,
        )

        self._capture_debug(
            model_role=model_role,
            system_prompt=self._last_system_prompt,
            messages=msgs,
            tools=tools,
            response=str(resp.content) if isinstance(resp.content, str) else "",
        )
        return resp

    async def chat(
        self,
        messages: list[BaseMessage],
        system_msgs: list[BaseMessage] | None = None,
        tools: list[dict[str, Any]] | None = None,
        on_token: Callable[[str], None] | None = None,
        interrupt_token: InterruptToken | None = None,
        context_hint: str = "",
        model_role: str = "medium",
        temperature: float | None = None,
        max_tokens: int | None = None,
        priority: int = 0,
        show_thinking: bool = False,
        modulation: ModulationState | None = None,
    ) -> AIMessage:
        mod = modulation or ModulationState()
        if system_msgs is None:
            system_msgs = self.build_system_messages(
                context_hint=context_hint,
                chaos_level=mod.chaos_level,
            )
        if show_thinking and messages and isinstance(messages[-1], HumanMessage):
            last_msg = messages[-1]
            last_msg.content = self._personality.build_thinking_prompt(str(last_msg.content))

        effective_temp = temperature if temperature is not None else mod.sampling_temperature

        return await self._call_llm(
            system_msgs,
            messages,
            model_role,
            max_tokens,
            temperature=effective_temp,
            tools=tools,
            on_token=on_token,
            interrupt_token=interrupt_token,
            priority=priority,
            enable_thinking=show_thinking,
        )

    def _capture_debug(
        self,
        model_role: str,
        system_prompt: str,
        messages: list[BaseMessage],
        tools: list[dict] | None,
        response: str,
        tool_iterations: list[dict] | None = None,
    ) -> None:
        from .capture import capture_debug as _capture

        _capture(
            debug_capture=self._debug_capture,
            model_config=self._model_config,
            model_role=model_role,
            system_prompt=system_prompt,
            messages=messages,
            response=response,
            tools=tools,
            tool_iterations=tool_iterations,
        )
