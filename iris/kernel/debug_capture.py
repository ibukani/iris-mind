from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from iris.llm.tokenizer_manager import TokenizerManager

from loguru import logger


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

    def format(self) -> str:
        lines: list[str] = []
        self._append_header(lines)
        self._append_system_prompt(lines)
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
            f"tools={tc.get('tools', 0)}  response={tc.get('response', 0)}  total={total}"
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


class DebugCapture:
    def __init__(
        self,
        max_entries: int = 10,
        output_dir: str = "logs/debug",
        tokenizer_mgr: TokenizerManager | None = None,
        auto_dump: bool = False,
    ) -> None:
        self._captures: list[CaptureEntry] = []
        self._max_entries = max_entries
        self._output_dir = Path(output_dir)
        self._tokenizer_mgr = tokenizer_mgr
        self._enabled = False
        self._auto_dump = auto_dump
        self._next_id = 1

    @property
    def enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, value: bool) -> None:
        self._enabled = value
        logger.info("DebugCapture: %s", "enabled" if value else "disabled")

    def count_tokens(self, text: str) -> int:
        if not text:
            return 0
        if self._tokenizer_mgr is not None:
            return self._tokenizer_mgr.estimate_tokens(text)
        return int(len(text) * 1.3)

    def capture(self, entry: CaptureEntry) -> None:
        if not self._enabled:
            return
        entry.id = self._next_id
        self._next_id += 1
        self._captures.append(entry)
        if len(self._captures) > self._max_entries:
            self._captures.pop(0)
        if self._auto_dump:
            self._write_file(entry)
        logger.info("DebugCapture: captured #%d (%d tok)", entry.id, entry.token_counts.get("total", 0))

    def last(self, n: int = 1) -> list[CaptureEntry]:
        return self._captures[-n:] if self._captures else []

    def list_captures(self) -> str:
        if not self._captures:
            return "No captures"
        lines = [f"Debug captures ({len(self._captures)}):"]
        lines.extend(e.format_short() for e in self._captures)
        return "\n".join(lines)

    def show(self, entry_id: int) -> str:
        for e in self._captures:
            if e.id == entry_id:
                return e.format()
        return f"Capture #{entry_id} not found"

    def dump_all(self) -> list[Path]:
        self._output_dir.mkdir(parents=True, exist_ok=True)
        written: list[Path] = []
        for e in self._captures:
            p = self._write_file(e)
            written.append(p)
        return written

    def _write_file(self, entry: CaptureEntry) -> Path:
        self._output_dir.mkdir(parents=True, exist_ok=True)
        path = self._output_dir / f"capture_{entry.id:03d}.txt"
        path.write_text(entry.format(), encoding="utf-8")
        logger.info("DebugCapture: wrote %s", path)
        return path
