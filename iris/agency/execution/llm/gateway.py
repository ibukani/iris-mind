from __future__ import annotations

from collections.abc import Callable
import datetime
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from loguru import logger

from iris.agency.execution.llm.prompt_builder import SystemPromptBuilder
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

    def set_session_roles_summary(self, summary: str) -> None:
        self._session_roles_summary = summary

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
    ) -> AIMessage:
        response_style = self._limbic.generate_response_style() if self._limbic else ""
        system_prompt = self._prompt_builder.build(
            context_hint=context_hint,
            response_style=response_style,
            session_roles_summary=self._session_roles_summary,
        )
        self._last_system_prompt = system_prompt
        self._last_call_model_role = model_role

        msgs: list[BaseMessage] = [SystemMessage(content=system_prompt), *messages]

        resp = await self._llm.chat(
            messages=msgs,
            model=self._model_config.get_model(model_role),
            temperature=self._model_config.get_effective_temperature(model_role),
            max_tokens=max_tokens or self._model_config.get_effective_max_tokens(model_role),
            tools=tools,
            on_token=on_token,
            interrupt_token=interrupt_token,
            priority=priority,
        )

        self._capture_debug(
            model_role=model_role,
            system_prompt=system_prompt,
            messages=msgs,
            tools=tools,
            response=str(resp.content) if isinstance(resp.content, str) else "",
        )

        return resp

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
        situation = plan.get("situation", "")
        content = plan.get("content", "")

        response_style = self._limbic.generate_response_style() if self._limbic and situation == "proactive" else ""

        system_prompt = self._prompt_builder.build(
            context_hint=context_hint,
            response_style=response_style,
            session_roles_summary=self._session_roles_summary,
            situation=situation,
        )

        msgs: list[BaseMessage] = [SystemMessage(content=system_prompt)]
        if messages and content:
            msgs.extend(messages)
        msgs.append(HumanMessage(content=content if content else "..."))

        temperature = plan.get("temperature", 0.5)
        max_tok = max_tokens or 80

        text = ""
        try:
            resp = await self._llm.chat(
                messages=msgs,
                model=self._model_config.get_model(model_role),
                max_tokens=max_tok,
                temperature=temperature,
                interrupt_token=interrupt_token,
                priority=priority,
            )
            text = str(resp.content).strip() if isinstance(resp.content, str) else ""
        except Exception as e:
            logger.debug("Short generation failed: %s", e)

        if not text:
            text = "" if situation == "proactive" else "…"

        self._capture_debug(
            model_role=model_role,
            system_prompt=system_prompt,
            messages=msgs,
            tools=None,
            response=text,
        )

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
            )
        )
