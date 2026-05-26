from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from iris.llm.tokenizer import TokenizerManager

from loguru import logger

from iris.kernel.capture_formatter import CaptureEntry


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
        logger.info("DebugCapture: {}", "enabled" if value else "disabled")

    def count_tokens(self, text: str) -> int:
        if not text:
            return 0
        if self._tokenizer_mgr is not None:
            return int(self._tokenizer_mgr.estimate_tokens(text))
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
        logger.info("DebugCapture: captured #{} ({} tok)", entry.id, entry.token_counts.get("total", 0))

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
        logger.info("DebugCapture: wrote {}", path)
        return path
