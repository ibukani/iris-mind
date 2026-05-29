from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class CaptureEntry:
    id: int
    timestamp: datetime
    model_name: str
    system_prompt: str
    messages: list[dict]
    tools: list[dict] | None
    response: str
    token_counts: dict
    tool_iterations: list[dict] = field(default_factory=list)
    full_prompt: str = ""

    def format(self) -> str:
        lines: list[str] = []
        self._append_header(lines)
        self._append_system_prompt(lines)
        self._append_full_prompt(lines)
        self._append_messages(lines)
        self._append_tools(lines)
        self._append_tool_iterations(lines)
        self._append_response(lines)
        self._append_footer(lines)
        return "\n".join(lines)

    def _append_header(self, lines: list[str]) -> None:
        sep = "=" * 80
        total = self.token_counts.get("total", 0)
        lines.append(sep)
        lines.append(f"DEBUG CAPTURE #{self.id}")
        lines.append(sep)
        lines.append(f"Time:   {self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"Model:  {self.model_name}")
        tc = self.token_counts
        lines.append(
            f"Tokens: system={tc.get('system', 0)}  history={tc.get('history', 0)}  "
            f"tools={tc.get('tools', 0)}  response={tc.get('response', 0)}  total={total}",
        )
        if self.tool_iterations:
            lines.append(f"Iterations: {len(self.tool_iterations)}")
        lines.append("")

    def _append_system_prompt(self, lines: list[str]) -> None:
        lines.append("-" * 80)
        lines.append("SYSTEM PROMPT")
        lines.append("-" * 80)
        lines.append(self.system_prompt)
        lines.append("")

    def _append_full_prompt(self, lines: list[str]) -> None:
        if not self.full_prompt:
            return
        lines.append("-" * 80)
        lines.append("FULL PROMPT (LLM に渡される最終形式)")
        lines.append("-" * 80)
        lines.append(self.full_prompt)
        lines.append("")

    def _append_messages(self, lines: list[str]) -> None:
        sep = "-" * 80
        lines.append(f"{sep}")
        lines.append(f"MESSAGES ({len(self.messages)})")
        lines.append(f"{sep}")
        for m in self.messages:
            role = m.get("role", "?")
            content = (m.get("content", "") or "")[:2000]
            ts = ""
            if "timestamp" in m:
                ts = f" ({m['timestamp'][:8]})"
            lines.append("")
            lines.append(f"[{role}]{ts}")
            lines.append(f"{'─' * 40}")
            lines.append(content)
        lines.append("")

    def _append_tools(self, lines: list[str]) -> None:
        if not self.tools:
            return
        sep = "-" * 80
        lines.append(f"{sep}")
        lines.append(f"TOOLS ({len(self.tools)} definitions)")
        lines.append(f"{sep}")
        for t in self.tools:
            fn = t.get("function", {})
            name = fn.get("name", "?")
            desc = fn.get("description", "")[:120]
            lines.append(f"  - {name}: {desc}")
        lines.append("")

    def _append_tool_iterations(self, lines: list[str]) -> None:
        if not self.tool_iterations:
            return
        sep = "-" * 80
        lines.append(f"{sep}")
        lines.append("TOOL ITERATIONS")
        lines.append(f"{sep}")
        for i, it in enumerate(self.tool_iterations, 1):
            lines.append("")
            lines.append(f"--- Iteration {i} ---")
            tc = it.get("tool_calls", [])
            for call in tc:
                fn = call.get("function", {})
                lines.append(f"  CALL: {fn.get('name', '?')}({fn.get('arguments', {})})")
            results = it.get("results", [])
            for name, result, _is_side in results:
                lines.append(f"  RESULT: {name} -> {str(result)[:200]}")
        lines.append("")

    def _append_response(self, lines: list[str]) -> None:
        sep = "-" * 80
        lines.append(f"{sep}")
        lines.append("RESPONSE")
        lines.append(f"{sep}")
        lines.append(self.response)
        lines.append("")

    def _append_footer(self, lines: list[str]) -> None:
        lines.append("=" * 80)

    def format_short(self) -> str:
        ts = self.timestamp.strftime("%H:%M:%S")
        total = self.token_counts.get("total", 0)
        rlen = self.token_counts.get("response", 0)
        return f"  #{self.id}  {ts}  {self.model_name}  {total}tok  response={rlen}"
