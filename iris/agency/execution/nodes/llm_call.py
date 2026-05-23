from __future__ import annotations

from typing import TYPE_CHECKING, Any

from iris.agency.execution.state import DynamicState, ExecutionState

if TYPE_CHECKING:
    from iris.agency.execution.engine import ToolEngine
    from iris.agency.execution.llm.gateway import LLMGateway
    from iris.llm.capability import CapabilityChecker

from loguru import logger


class LLMCallNode:
    def __init__(
        self,
        pipeline: LLMGateway,
        tool_executor: ToolEngine | None = None,
        capability_checker: CapabilityChecker | None = None,
        dynamic: DynamicState | None = None,
    ) -> None:
        self._pipeline = pipeline
        self._tool_executor = tool_executor
        self._capability_checker = capability_checker
        self._dynamic = dynamic or DynamicState()

    async def __call__(self, state: ExecutionState) -> None:
        if state.get("interrupted"):
            return

        plan = state["plan"]
        tools_allowed = plan.get("tools_allowed", True)
        model_role = plan.get("model_role", "default")
        priority = plan.get("priority", 0)

        try:
            if not tools_allowed:
                response_text = await self._pipeline.chat_short(
                    messages=state["messages"],
                    plan=plan,
                    model_role=model_role,
                    max_tokens=plan.get("max_tokens", 0) or None,
                    priority=priority,
                    interrupt_token=self._dynamic.interrupt_token,
                )
                state["response_text"] = response_text
            else:
                tools = self._get_tools(plan.get("allow_side_effects", True), model_role)
                max_tokens = plan.get("max_tokens", 0) or None
                context_hint = plan.get("context_hint", "")

                resp = await self._pipeline.chat(
                    messages=state["messages"],
                    tools=tools,
                    on_token=self._dynamic.on_token,
                    interrupt_token=self._dynamic.interrupt_token,
                    context_hint=context_hint,
                    model_role=model_role,
                    max_tokens=max_tokens,
                    priority=priority,
                )

                state["messages"].append(resp)
                content = resp.content
                state["response_text"] = str(content).strip() if isinstance(content, str) else ""

        except Exception as e:
            logger.exception("LLM generation failed")
            state["error"] = str(e)

    def _get_tools(self, allow_side_effects: bool, model_role: str) -> list[dict[str, Any]] | None:
        if self._tool_executor is None:
            return None
        tools = self._tool_executor.registry.list_tools(allow_side_effects=allow_side_effects) or None
        if tools and self._capability_checker and not self._capability_checker.supports_tools(model_role):
            return None
        return tools
