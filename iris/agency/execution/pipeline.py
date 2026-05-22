from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import datetime
import logging
from typing import Any

from iris.agency.execution.tool_executor import ToolExecutionEngine
from iris.agency.execution.workflow import IrisExecutionWorkflow
from iris.kernel.config import ModelConfig
from iris.kernel.debug_capture import CaptureEntry, DebugCapture
from iris.limbic.manager import LimbicManager
from iris.llm.capability_checker import CapabilityChecker
from iris.llm.interrupt_token import InterruptToken
from iris.llm.llm_bridge import LLMBridge
from iris.llm.prompt_builder import Personality
from iris.memory.long_term.stores import AgentsMdStore
from iris.memory.manager import MemoryManager
from iris.memory.persona_profile import PersonaProfile

logger = logging.getLogger(__name__)

_SITUATION_INSTRUCTIONS: dict[str, str] = {
    "proactive": (
        "## 状況: 自発的な一声\n"
        "時間帯や会話の流れに合わせて、自然に声をかけてください。\n"
        "誰かと会話しているのではなく、自ら会話を始める場面です。"
    ),
}


@dataclass
class _PersonalityContext:
    agents_md: str
    current_state: str
    speech_style: str
    personality_traits: str
    user_prefs: str


class SystemPromptBuilder:
    def __init__(
        self,
        personality: Personality,
        agents_md_store: AgentsMdStore | None = None,
        persona_profile: PersonaProfile | None = None,
        memory: MemoryManager | None = None,
        limbic: LimbicManager | None = None,
        governance_principles: str = "",
    ) -> None:
        self._personality = personality
        self._agents_md_store = agents_md_store
        self._persona_profile = persona_profile
        self._memory = memory
        self._limbic = limbic
        self._governance_principles = governance_principles

    def build(
        self,
        context_hint: str = "",
        response_style: str = "",
        session_roles_summary: str = "",
    ) -> str:
        pctx = self._load_personality_context()

        prompt = self._personality.build_system_prompt(
            agents_md_content=pctx.agents_md,
            user_preferences=pctx.user_prefs,
            session_roles=session_roles_summary,
            response_style=response_style,
            speech_style=pctx.speech_style,
            personality_traits=pctx.personality_traits,
            governance_principles=self._governance_principles,
        )

        prompt += f"\n\n## 現在日時\n{self._build_time_string()}"

        if self._limbic:
            mood_desc = self._limbic.build_mood_description()
            if mood_desc:
                prompt += f"\n\n## 現在の気分\n{mood_desc}"

        if pctx.current_state and "{speech_style}" not in self._personality.system_prompt_template:
            prompt += f"\n\n{pctx.current_state}"

        if context_hint:
            prompt += f"\n\n## 会話コンテキスト\n{context_hint}"

        return prompt

    def build_full(
        self,
        context_hint: str,
        response_style: str,
        situation: str,
        session_roles_summary: str = "",
    ) -> str:
        prompt = self.build(
            context_hint=context_hint,
            response_style=response_style,
            session_roles_summary=session_roles_summary,
        )
        if situation in _SITUATION_INSTRUCTIONS:
            prompt += "\n\n" + _SITUATION_INSTRUCTIONS[situation]
        return prompt

    def _load_personality_context(self) -> _PersonalityContext:
        agents_md = self._agents_md_store.load() if self._agents_md_store else ""
        current_state = self._persona_profile.get_current_state_section() if self._persona_profile else ""
        speech_style = self._persona_profile.get_speech_style() if self._persona_profile else ""
        personality_traits = self._persona_profile.get_traits() if self._persona_profile else ""
        user_prefs = self._build_user_preferences_section()
        return _PersonalityContext(
            agents_md=agents_md,
            current_state=current_state,
            speech_style=speech_style,
            personality_traits=personality_traits,
            user_prefs=user_prefs,
        )

    def _build_user_preferences_section(self) -> str:
        prefs_list = self._memory.get_user_preferences() if self._memory else []
        seen: set[str] = set()
        unique_prefs: list[str] = []
        for p in prefs_list:
            c = p.get("content", "").strip()
            if c and c not in seen:
                seen.add(c)
                unique_prefs.append(f"- {c}")
        return "\n".join(unique_prefs)

    @staticmethod
    def _build_time_string() -> str:
        dt_now = datetime.datetime.now()
        weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        return f"{dt_now.strftime('%Y-%m-%d %H:%M:%S')} ({weekdays[dt_now.weekday()]})"


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
        self._tool_executor = tool_executor
        self._capability_checker = capability_checker
        self._debug_capture = debug_capture
        self._session_roles_summary: str = ""
        self._max_tool_iterations: int = 3
        self._sysprompt_cache: str | None = None
        self._last_system_prompt: str = ""
        self._last_call_model_role: str = "default"

        self._prompt_builder = SystemPromptBuilder(
            personality=personality,
            agents_md_store=agents_md_store,
            persona_profile=persona_profile,
            memory=memory,
            limbic=limbic,
            governance_principles=governance_principles,
        )

    def set_session_roles_summary(self, summary: str) -> None:
        self._session_roles_summary = summary

    def _get_tools(self, allow_side_effects: bool = True) -> list[dict[str, Any]] | None:
        if self._tool_executor is None:
            return None
        return self._tool_executor.registry.list_tools(allow_side_effects=allow_side_effects) or None

    async def call(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        on_token: Callable[[str], None] | None = None,
        interrupt_token: InterruptToken | None = None,
        context_hint: str = "",
        model_role: str = "default",
        max_tokens: int | None = None,
        priority: int = 0,
    ) -> dict[str, Any]:
        self._sysprompt_cache = None
        response_style = ""
        if self._prompt_builder._limbic:
            response_style = self._prompt_builder._limbic.build_response_style()
        system_prompt = self._prompt_builder.build(
            context_hint=context_hint,
            response_style=response_style,
            session_roles_summary=self._session_roles_summary,
        )
        self._last_system_prompt = system_prompt
        self._last_call_model_role = model_role

        msgs: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}, *messages]

        return await self._llm.chat(
            messages=msgs,
            model=self._model_config.get_model(model_role),
            temperature=self._model_config.get_effective_temperature(model_role),
            max_tokens=max_tokens or self._model_config.get_effective_max_tokens(model_role),
            tools=tools,
            on_token=on_token,
            interrupt_token=interrupt_token,
            priority=priority,
        )

    async def generate(
        self,
        plan: dict[str, Any],
        messages: list[dict[str, Any]],
        on_token: Callable[[str], None] | None = None,
        interrupt_token: InterruptToken | None = None,
    ) -> str:
        self._sysprompt_cache = None
        model_role: str = plan.get("model_role", "default")
        context_hint: str = plan.get("context_hint", "")
        max_tokens: int | None = plan.get("max_tokens", 0) or None
        priority: int = plan.get("priority", 0)

        if not plan.get("tools_allowed", True):
            temperature: float = plan.get("temperature", 0.5)
            return await self._generate_without_tools(
                plan,
                messages,
                max_tokens,
                temperature,
                model_role=model_role,
                interrupt_token=interrupt_token,
                priority=priority,
            )

        allow_side_effects: bool = plan.get("allow_side_effects", True)
        max_tool_iters = plan.get("max_tool_iterations")

        return await self._generate_with_tools(
            messages,
            context_hint=context_hint,
            on_token=on_token,
            interrupt_token=interrupt_token,
            model_role=model_role,
            max_tokens=max_tokens,
            allow_side_effects=allow_side_effects,
            max_tool_iterations=max_tool_iters,
            priority=priority,
        )

    async def _generate_without_tools(
        self,
        plan: dict[str, Any],
        messages: list[dict[str, Any]],
        max_tokens: int | None,
        temperature: float,
        model_role: str = "default",
        interrupt_token: InterruptToken | None = None,
        priority: int = 0,
    ) -> str:
        context_hint: str = plan.get("context_hint", "")
        situation: str = plan.get("situation", "")
        content: str = plan.get("content", "")

        response_style = ""
        if situation == "proactive" and self._prompt_builder._limbic:
            response_style = self._prompt_builder._limbic.build_response_style()

        system_prompt = self._prompt_builder.build_full(
            context_hint=context_hint,
            response_style=response_style,
            situation=situation,
            session_roles_summary=self._session_roles_summary,
        )

        msgs: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
        if messages and content:
            msgs.extend(messages)
        msgs.append({"role": "user", "content": content if content else "..."})

        text = ""
        try:
            resp = await self._llm.chat(
                messages=msgs,
                model=self._model_config.get_model(model_role),
                max_tokens=max_tokens or 80,
                temperature=temperature,
                interrupt_token=interrupt_token,
                priority=priority,
            )
            text = str((resp.get("message", {}) or {}).get("content", "")).strip()
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

    async def _generate_with_tools(
        self,
        messages: list[dict],
        on_token: Callable[[str], None] | None = None,
        interrupt_token: InterruptToken | None = None,
        context_hint: str = "",
        model_role: str = "default",
        max_tokens: int | None = None,
        allow_side_effects: bool = True,
        max_tool_iterations: int | None = None,
        priority: int = 0,
    ) -> str:
        tools = self._get_tools(allow_side_effects=allow_side_effects)
        if tools and self._capability_checker and not self._capability_checker.supports_tools(model_role):
            tools = None

        workflow = IrisExecutionWorkflow(
            llm=self._llm,
            model_config=self._model_config,
            tool_executor=self._tool_executor,
            max_tool_iterations=max_tool_iterations if max_tool_iterations is not None else self._max_tool_iterations,
            interrupt_token=interrupt_token,
            timeout=None,
        )

        try:
            final_text = await workflow.run(
                messages=messages,
                model_role=model_role,
                max_tokens=max_tokens,
                tools=tools,
                context_hint=context_hint,
                iteration=0,
                priority=priority,
            )
        except Exception as e:
            logger.error("Workflow failed: %s", e)
            final_text = ""

        sys_prompt = getattr(self, "_last_system_prompt", "")
        self._capture_debug(
            model_role=model_role,
            system_prompt=sys_prompt,
            messages=messages,
            tools=tools,
            response=str(final_text),
            tool_iterations=workflow.get_tool_iterations_log(),
        )

        return str(final_text)

    def _capture_debug(
        self,
        model_role: str,
        system_prompt: str,
        messages: list[dict],
        tools: list[dict] | None,
        response: str,
        tool_iterations: list[dict] | None = None,
    ) -> None:
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
