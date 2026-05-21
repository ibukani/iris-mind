from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from iris.llm.tokenizer_manager import TokenizerManager

logger = logging.getLogger(__name__)


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

    def format_as_markdown(self) -> str:
        total = self.token_counts.get("total", 0)
        lines = [
            f"# Debug Capture #{self.id}",
            f"**Time**: {self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
            f"**Model**: {self.model_name}",
            f"**Tokens**: system={self.token_counts.get('system', 0)} "
            f"history={self.token_counts.get('history', 0)} "
            f"tools={self.token_counts.get('tools', 0)} "
            f"response={self.token_counts.get('response', 0)} "
            f"**total={total}**",
        ]
        if self.tool_iterations:
            lines.append(f"**Tool iterations**: {len(self.tool_iterations)}")

        lines.append("")
        lines.append("## System Prompt")
        lines.append("```markdown")
        lines.append(self.system_prompt)
        lines.append("```")

        lines.append("")
        lines.append(f"## Messages ({len(self.messages)})")
        for m in self.messages:
            role = m.get("role", "?")
            content = (m.get("content", "") or "")[:2000]
            ts = ""
            if "timestamp" in m:
                ts = f" ({m['timestamp'][:8]})"
            lines.append(f"### {role}{ts}")
            lines.append(content)

        if self.tools:
            lines.append("")
            lines.append(f"## Tools ({len(self.tools)} definitions)")
            for t in self.tools:
                fn = t.get("function", {})
                name = fn.get("name", "?")
                desc = fn.get("description", "")[:120]
                lines.append(f"- **{name}**: {desc}")

        if self.tool_iterations:
            lines.append("")
            lines.append("## Tool Iterations")
            for i, it in enumerate(self.tool_iterations, 1):
                lines.append(f"### Iteration {i}")
                tc = it.get("tool_calls", [])
                for call in tc:
                    fn = call.get("function", {})
                    lines.append(f"- CALL: {fn.get('name', '?')}({fn.get('arguments', {})})")
                results = it.get("results", [])
                for name, result, _is_side in results:
                    lines.append(f"- RESULT: {name} → {str(result)[:200]}")

        lines.append("")
        lines.append("## Response")
        lines.append(self.response)

        return "\n".join(lines)

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
    ) -> None:
        self._captures: list[CaptureEntry] = []
        self._max_entries = max_entries
        self._output_dir = Path(output_dir)
        self._tokenizer_mgr = tokenizer_mgr
        self._enabled = False
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
                return e.format_as_markdown()
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
        path = self._output_dir / f"capture_{entry.id:03d}.md"
        path.write_text(entry.format_as_markdown(), encoding="utf-8")
        logger.info("DebugCapture: wrote %s", path)
        return path
