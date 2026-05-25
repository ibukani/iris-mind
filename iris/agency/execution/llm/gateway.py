from __future__ import annotations

from collections.abc import Callable
import datetime
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from loguru import logger

from iris.agency.execution.llm.prompt_builder import SystemPromptBuilder
from iris.agency.planning.emotion_temperature import EmotionTemperatureModulator
from iris.kernel.config import ModelConfig
from iris.kernel.debug_capture import CaptureEntry, DebugCapture
from iris.limbic.manager import LimbicManager
from iris.llm.bridge import LLMBridge
from iris.llm.capability import CapabilityChecker
from iris.llm.interrupt_token import InterruptToken
from iris.llm.prompt import Personality
from iris.memory.long_term.stores import AgentsMdStore
from iris.memory.manager import MemoryManager
from iris.memory.persona_profile import PersonaProfile


class LLMGateway:
    def __init__(
        self,
        llm: LLMBridge,
        model_config: ModelConfig,
        personality: Personality,
        agents_md_store: AgentsMdStore | None = None,
        persona_profile: PersonaProfile | None = None,
        memory: MemoryManager | None = None,
        limbic: LimbicManager | None = None,
        capability_checker: CapabilityChecker | None = None,
        debug_capture: DebugCapture | None = None,
    ) -> None:
        self._llm = llm
        self._model_config = model_config
        self._personality = personality
        self._limbic = limbic
        self._capability_checker = capability_checker
        self._debug_capture = debug_capture
        self._session_roles_summary: str = ""
        self._last_system_prompt: str = ""
        self._last_call_model_role: str = "default"

        self._prompt_builder = SystemPromptBuilder(
            personality=personality,
            agents_md_store=agents_md_store,
            persona_profile=persona_profile,
            memory=memory,
            limbic=limbic,
        )

    @staticmethod
    def _build_full_prompt(msgs: list[BaseMessage]) -> str:
        lines: list[str] = []
        for m in msgs:
            role = getattr(m, "type", "unknown")
            content = str(m.content) if m.content else ""
            lines.append(f"[{role}]\n{content}")
        return "\n\n".join(lines)

    def set_session_roles_summary(self, summary: str) -> None:
        self._session_roles_summary = summary

    def _build_system_messages(
        self,
        context_hint: str,
        response_style: str = "",
        situation: str = "",
    ) -> list[BaseMessage]:
        return self._prompt_builder.build(
            context_hint=context_hint,
            response_style=response_style,
            session_roles_summary=self._session_roles_summary,
            situation=situation,
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
        self._last_system_prompt = str(system_msgs[0].content) if system_msgs else ""
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
        tools: list[dict[str, Any]] | None = None,
        on_token: Callable[[str], None] | None = None,
        interrupt_token: InterruptToken | None = None,
        context_hint: str = "",
        model_role: str = "default",
        max_tokens: int | None = None,
        priority: int = 0,
        show_thinking: bool = False,
    ) -> AIMessage:
        response_style = self._limbic.generate_response_style() if self._limbic else ""
        system_msgs = self._build_system_messages(
            context_hint=context_hint,
            response_style=response_style,
        )
        if show_thinking and messages and isinstance(messages[-1], HumanMessage):
            last_msg = messages[-1]
            last_msg.content = self._personality.build_thinking_prompt(str(last_msg.content))

        return await self._call_llm(
            system_msgs,
            messages,
            model_role,
            max_tokens,
            tools=tools,
            on_token=on_token,
            interrupt_token=interrupt_token,
            priority=priority,
            enable_thinking=show_thinking,
        )

    async def chat_short(
        self,
        messages: list[BaseMessage],
        plan: dict[str, Any],
        model_role: str = "default",
        max_tokens: int | None = None,
        priority: int = 0,
        interrupt_token: InterruptToken | None = None,
    ) -> str:
        context_hint = plan.get("context_hint", "")
        reason = plan.get("reason", "")
        content = plan.get("content", "")

        is_proactive = reason in ("proactive_curiosity", "proactive_escalation", "timer")
        response_style = self._limbic.generate_response_style() if self._limbic and is_proactive else ""

        system_msgs = self._build_system_messages(
            context_hint=context_hint,
            response_style=response_style,
            situation="proactive" if is_proactive else "",
        )

        msgs: list[BaseMessage] = []
        if messages and content:
            msgs.extend(messages)
        msgs.append(HumanMessage(content=content or "..."))

        temperature = (
            EmotionTemperatureModulator.compute_temperature(self._limbic.current_emotion())
            if self._limbic
            else EmotionTemperatureModulator.DEFAULT_TEMPERATURE
        )
        max_tok = max_tokens or 80

        try:
            resp = await self._call_llm(
                system_msgs,
                msgs,
                model_role,
                max_tok,
                temperature=temperature,
                interrupt_token=interrupt_token,
                priority=priority,
            )
            text = str(resp.content).strip() if isinstance(resp.content, str) else ""
        except Exception as e:
            logger.debug("Short generation failed: {}", e)
            text = ""

        if not text:
            text = "" if is_proactive else "…"

        return text

    def _capture_debug(
        self,
        model_role: str,
        system_prompt: str,
        messages: list[BaseMessage],
        tools: list[dict] | None,
        response: str,
        tool_iterations: list[dict] | None = None,
    ) -> None:
        dc = self._debug_capture
        if not (dc and dc.enabled):
            return

        model_name = self._model_config.get_model(model_role)
        history_msgs = [m for m in messages if not isinstance(m, SystemMessage)]
        tc = {
            "system": dc.count_tokens(system_prompt),
            "history": dc.count_tokens(" ".join(str(m.content) for m in history_msgs)),
            "tools": dc.count_tokens(str(tools)) if tools else 0,
            "response": dc.count_tokens(response),
        }
        tc["total"] = sum(tc.values())

        dc.capture(
            CaptureEntry(
                id=0,
                timestamp=datetime.datetime.now(),
                model_name=model_name,
                system_prompt=system_prompt,
                messages=[{"role": m.type, "content": m.content} for m in history_msgs],
                tools=tools,
                response=response,
                token_counts=tc,
                tool_iterations=tool_iterations or [],
                full_prompt=self._build_full_prompt(messages),
            ),
        )
