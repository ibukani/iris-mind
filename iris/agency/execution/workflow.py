from __future__ import annotations

import logging
from typing import Any

from llama_index.core.workflow import Event, StartEvent, StopEvent, Workflow, step

from iris.agency.execution.tool_executor import ToolExecutionEngine
from iris.kernel.config import ModelConfig
from iris.llm.interrupt_token import InterruptToken
from iris.llm.llm_bridge import LLMBridge

logger = logging.getLogger(__name__)


class InputEvent(Event):
    messages: list[dict[str, Any]]
    model_role: str
    max_tokens: int | None
    tools: list[dict[str, Any]] | None
    context_hint: str
    iteration: int
    priority: int = 0


class ToolCallEvent(Event):
    messages: list[dict[str, Any]]
    tool_calls: list[dict[str, Any]]
    model_role: str
    max_tokens: int | None
    tools: list[dict[str, Any]] | None
    context_hint: str
    iteration: int
    priority: int = 0


class IrisExecutionWorkflow(Workflow):
    MAX_TOOL_OUTPUT_LENGTH = 200

    def __init__(
        self,
        llm: LLMBridge,
        model_config: ModelConfig,
        tool_executor: ToolExecutionEngine | None,
        max_tool_iterations: int = 3,
        interrupt_token: InterruptToken | None = None,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._llm = llm
        self._model_config = model_config
        self._tool_executor = tool_executor
        self._max_tool_iterations = max_tool_iterations
        self._interrupt_token = interrupt_token
        self._tool_iterations_log: list[dict[str, Any]] = []

    def get_tool_iterations_log(self) -> list[dict[str, Any]]:
        return self._tool_iterations_log

    @step
    async def generate_step(self, ev: StartEvent | InputEvent) -> ToolCallEvent | StopEvent:
        if self._interrupt_token and self._interrupt_token.is_cancelled:
            logger.debug("Workflow interrupted in generate_step.")
            return StopEvent(result="")

        # Retrieve attributes depending on event type
        if isinstance(ev, StartEvent):
            messages = ev.get("messages", [])
            model_role = ev.get("model_role", "default")
            max_tokens = ev.get("max_tokens", None)
            tools = ev.get("tools", None)
            context_hint = ev.get("context_hint", "")
            iteration = ev.get("iteration", 0)
            priority = ev.get("priority", 0)
        else:
            messages = ev.messages
            model_role = ev.model_role
            max_tokens = ev.max_tokens
            tools = ev.tools
            context_hint = ev.context_hint
            iteration = ev.iteration
            priority = ev.priority

        if iteration >= self._max_tool_iterations:
            logger.warning("Max tool iterations reached.")
            return StopEvent(result="")

        model = self._model_config.get_model(model_role)
        temp = self._model_config.get_effective_temperature(model_role)
        max_tok = max_tokens or self._model_config.get_effective_max_tokens(model_role)

        try:
            resp = await self._llm.chat(
                messages=messages,
                model=model,
                temperature=temp,
                max_tokens=max_tok,
                tools=tools,
                interrupt_token=self._interrupt_token,
                priority=priority,
            )
        except Exception as e:
            logger.error("LLM execution failed: %s", e)
            return StopEvent(result="")

        msg = resp.get("message", {})
        tool_calls = msg.get("tool_calls")

        if not tool_calls or self._tool_executor is None:
            final_text = str(msg.get("content", "") or "")
            return StopEvent(result=final_text)

        messages.append(msg)
        return ToolCallEvent(
            messages=messages,
            tool_calls=tool_calls,
            model_role=model_role,
            max_tokens=max_tokens,
            tools=tools,
            context_hint=context_hint,
            iteration=iteration + 1,
            priority=priority,
        )

    @step
    async def execute_tools_step(self, ev: ToolCallEvent) -> InputEvent | StopEvent:
        if self._interrupt_token and self._interrupt_token.is_cancelled:
            logger.debug("Workflow interrupted in execute_tools_step.")
            return StopEvent(result="")

        if self._tool_executor is None:
            return StopEvent(result="")

        results = self._tool_executor.execute_all(ev.messages)
        self._tool_iterations_log.append({"tool_calls": ev.tool_calls, "results": results})

        if self._tool_executor.all_side_effects(results):
            return StopEvent(result="")

        non_side_effects_count = sum(1 for r in results if not r[2])
        if non_side_effects_count > 0:
            for m in ev.messages[-non_side_effects_count:]:
                if m.get("role") == "tool":
                    content = str(m.get("content", ""))
                    if len(content) > self.MAX_TOOL_OUTPUT_LENGTH:
                        m["content"] = content[: self.MAX_TOOL_OUTPUT_LENGTH] + "..."

        return InputEvent(
            messages=ev.messages,
            model_role=ev.model_role,
            max_tokens=ev.max_tokens,
            tools=ev.tools,
            context_hint=ev.context_hint,
            iteration=ev.iteration,
            priority=ev.priority,
        )
