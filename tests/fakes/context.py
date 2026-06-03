"""Fake ContextManager (LLM context window の縮約動作をモック)。"""

from __future__ import annotations


class FakeContextManager:
    def __init__(self) -> None:
        self.has_summary = False
        self._summary = ""
        self._compact_messages: list[dict] = []

    def check_and_summarize(
        self,
        messages: list[dict],
        context_window: int,
        threshold: float = 0.7,
        preserve_last: int = 4,
    ) -> str:
        return self._summary

    def force_summarize(self, messages: list[dict], instructions: str = "", preserve_last: int = 2) -> str:
        self.has_summary = True
        self._summary = "Fake summary"
        return self._summary

    def build_compact_messages(self, messages: list[dict], preserve_last: int = 4) -> list[dict]:
        return self._compact_messages or [
            {"role": "system", "content": f"[Compact summary of {len(messages)} messages]"},
        ]

    def clear(self) -> None:
        self.has_summary = False
        self._summary = ""
        self._compact_messages.clear()


__all__ = ["FakeContextManager"]
