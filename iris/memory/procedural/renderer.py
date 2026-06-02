"""Style memory をプロンプトに注入するレンダラ。"""

from __future__ import annotations

from collections.abc import Iterable

from iris.memory.procedural.models import StyleMemory
from iris.memory.procedural.style_store import StyleMemoryStore

_KIND_PREFIX: dict[str, str] = {
    "tone_preference": "[tone]",
    "successful_pattern": "[pattern]",
    "running_gag": "[gag]",
    "avoidance_rule": "[avoid]",
    "chaos_preference": "[chaos]",
    "conversation_strategy": "[strategy]",
}


def render_style_hints(
    items: Iterable[StyleMemory],
    *,
    max_chars: int = 800,
) -> str:
    """``StyleMemory`` のリストをプロンプト用の自然言語ヒントに変換する。"""
    lines: list[str] = []
    for m in items:
        prefix = _KIND_PREFIX.get(m.kind, "[hint]")
        if m.activation_condition:
            line = f"- {prefix} {m.content} (発動条件: {m.activation_condition})"
        else:
            line = f"- {prefix} {m.content}"
        lines.append(line)
    text = "\n".join(lines)
    if len(text) > max_chars:
        text = text[: max_chars - 1] + "…"
    return text


def build_style_hints(
    store: StyleMemoryStore,
    *,
    account_id: str = "",
    room_id: str = "",
    max_items: int = 4,
    max_chars: int = 800,
) -> str:
    items = store.list_enabled(account_id=account_id, room_id=room_id, max_items=max_items)
    if not items:
        return ""
    return render_style_hints(items, max_chars=max_chars)


__all__ = ["build_style_hints", "render_style_hints"]
