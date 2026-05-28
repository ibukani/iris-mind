from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from langchain_core.messages import BaseMessage

from iris.agency.execution.models import DynamicState, ExecutionState
from iris.agency.execution.node_type import NODE_TYPES, ROUTING_TOOLS
from iris.agency.planning.models import Plan
from iris.agency.task_level import TASK_LEVELS, TaskLevel

if TYPE_CHECKING:
    from iris.agency.execution.engine import ToolEngine
    from iris.agency.execution.llm.gateway import LLMGateway
    from iris.event.event_bus import EventBus
    from iris.llm.capability import CapabilityChecker
    from iris.memory.manager import MemoryManager

from loguru import logger


def _routing_tool_schema(name: str) -> dict[str, Any]:
    desc = ROUTING_TOOLS[name]["description"]
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": desc,
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    }


class BaseLLMNode(ABC):
    def __init__(
        self,
        pipeline: LLMGateway,
        tool_executor: ToolEngine | None = None,
        capability_checker: CapabilityChecker | None = None,
        dynamic: DynamicState | None = None,
        event_bus: EventBus | None = None,
        memory: MemoryManager | None = None,
    ) -> None:
        self._pipeline = pipeline
        self._tool_executor = tool_executor
        self._capability_checker = capability_checker
        self._dynamic = dynamic or DynamicState()
        self._event_bus = event_bus
        self._memory = memory

    @property
    @abstractmethod
    def node_type_name(self) -> str: ...

    def _current_level_name(self, state: ExecutionState) -> str:
        nt = NODE_TYPES[self.node_type_name]
        idx = state["current_level_idx"]
        if 0 <= idx < len(nt.available_levels):
            return nt.available_levels[idx]
        logger.warning("level_idx {} out of range for {}, fallback to entry", idx, nt.name)
        return nt.entry_level

    def _get_tools(self, level_name: str, plan: Plan) -> list[dict[str, Any]] | None:
        if self._tool_executor is None:
            return None
        nt = NODE_TYPES[self.node_type_name]
        names = nt.tool_list_by_level.get(level_name)
        allow_side_effects = plan.overrides.get("allow_side_effects", True)
        if names is not None:
            return self._tool_executor.list_tools_by_name(names, allow_side_effects) or None
        tools = self._tool_executor.registry.list_tools(allow_side_effects=allow_side_effects)
        if tools and self._capability_checker:
            level = TASK_LEVELS[level_name]
            if not self._capability_checker.supports_tools(level.model_role):
                return None
        return tools or None

    def _build_routing_tools(self, state: ExecutionState) -> list[dict[str, Any]]:
        nt = NODE_TYPES[self.node_type_name]
        if state["chain_depth"] >= nt.max_chain_depth:
            targets = [t for t in nt.routing_targets if t != nt.name]
        else:
            targets = nt.routing_targets
        return [_routing_tool_schema(name) for name in targets]

    def _build_system_prompt(
        self,
        state: ExecutionState,
        level: TaskLevel,
        plan: Plan,
    ) -> list[BaseMessage] | None:
        return self._pipeline.build_system_messages(
            context_hint=plan.context_hint,
            node_type=self.node_type_name,
            chaos_level=plan.modulation.chaos_level,
        )

    def _build_chat_params(
        self,
        state: ExecutionState,
        level: TaskLevel,
        plan: Plan,
    ) -> dict[str, Any]:
        return {
            "model_role": level.model_role,
            "temperature": level.temperature,
            "max_tokens": level.max_tokens or None,
            "priority": level.priority,
            "show_thinking": level.show_thinking,
            "modulation": plan.modulation,
        }

    def _resolve_chat_params(
        self,
        state: ExecutionState,
        level: TaskLevel,
        plan: Plan,
    ) -> dict[str, Any]:
        params = self._build_chat_params(state, level, plan)
        # Planning overrides
        if "priority" in plan.overrides:
            params["priority"] = plan.overrides["priority"]
        # TaskLevel caps: can only reduce, never exceed TaskLevel
        if params.get("max_tokens") is not None and level.max_tokens > 0:
            params["max_tokens"] = min(params["max_tokens"], level.max_tokens)
        if params.get("temperature") is not None and level.temperature is not None:
            params["temperature"] = min(params["temperature"], level.temperature)
        return params

    async def __call__(self, state: ExecutionState) -> dict[str, Any] | None:
        if state.get("interrupted"):
            return None

        plan = state["plan"]
        level_name = self._current_level_name(state)
        level = TASK_LEVELS[level_name]

        try:
            system_msgs = self._build_system_prompt(state, level, plan)
            tools = self._get_tools(level_name, plan)
            routing_tools = self._build_routing_tools(state)

            all_tools: list[dict[str, Any]] | None = None
            if tools or routing_tools:
                all_tools = (tools or []) + routing_tools

            resp = await self._pipeline.chat(
                messages=list(state["messages"]),
                system_msgs=system_msgs,
                tools=all_tools,
                on_token=self._dynamic.on_token,
                interrupt_token=self._dynamic.interrupt_token,
                **self._resolve_chat_params(state, level, plan),
            )

            if self._dynamic.interrupt_token and self._dynamic.interrupt_token.is_cancelled:
                state["interrupted"] = True
                return {"response_text": "", "interrupted": True}

            state["messages"].append(resp)

            raw = resp.content
            response_text = raw.strip() if isinstance(raw, str) else ""

            if response_text and self._memory:
                self._memory.short_term.add_turn("assistant", response_text, plan.user_identity)

            return {"response_text": response_text}
        except Exception:
            logger.exception("LLM node error in {}", self.node_type_name)
            return {"error": "LLM call failed", "response_text": ""}
