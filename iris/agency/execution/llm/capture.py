from __future__ import annotations

import datetime
from typing import Any

from langchain_core.messages import BaseMessage, SystemMessage

from iris.kernel.config import ModelConfig
from iris.kernel.debug_capture import CaptureEntry, DebugCapture


def build_full_prompt(msgs: list[BaseMessage]) -> str:
    lines: list[str] = []
    for m in msgs:
        role = getattr(m, "type", "unknown")
        content = str(m.content) if m.content else ""
        lines.append(f"[{role}]\n{content}")
    return "\n\n".join(lines)


def capture_debug(
    debug_capture: DebugCapture | None,
    model_config: ModelConfig,
    model_role: str,
    system_prompt: str,
    messages: list[BaseMessage],
    response: str,
    tools: list[dict[str, Any]] | None = None,
    tool_iterations: list[dict[str, Any]] | None = None,
) -> None:
    dc = debug_capture
    if not (dc and dc.enabled):
        return

    model_name = model_config.get_model(model_role)
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
            full_prompt=build_full_prompt(messages),
        ),
    )
