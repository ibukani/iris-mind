from __future__ import annotations

from collections.abc import Callable

from iris.memory.models import ContentBlock, block_tag
from iris.memory.short_term.models import SearchResult, TurnData


def _render_blocks(blocks: list[ContentBlock], max_chars: int = 100) -> str:
    parts: list[str] = []
    remaining = max_chars
    for b in blocks or []:
        if remaining <= 0:
            break
        tag = block_tag(b)
        if len(tag) > remaining:
            tag = tag[: remaining - 3] + "..."
        if tag:
            parts.append(tag)
            remaining -= len(tag)
    return " ".join(parts) if parts else ""


def render_short_term_context(
    turns: list[TurnData],
    active_references: set[str],
    search_fn: Callable[..., list[SearchResult]],
    max_chars: int = 600,
    query: str | None = None,
    active_users: list[tuple[str, str]] | None = None,
    room_id: str = "",
) -> str:
    if not turns:
        return ""
    if room_id:
        turns = [t for t in turns if t.get("room_id", "") == room_id]
    parts: list[str] = []

    chat_turns = [t for t in turns if t.get("role") not in ("system",)]
    if not chat_turns and not query:
        if active_users:
            user_lines = [f"- {nick}" for _, nick in active_users]
            parts.append("### 現在の参加者")
            parts.extend(user_lines)
            text = "\n".join(parts)
            if len(text) > max_chars:
                text = text[: max_chars - 3] + "..."
            return text
        return ""

    if query:
        parts.append("### 直近の会話（関連）")
        relevant = search_fn(query, max_results=3)
        shown_indices = {r.get("index", -1) for r in relevant}
        for r in relevant:
            role = r.get("role", "system")
            uid = r.get("user_id", "")
            label = uid or ("User" if role == "user" else "Iris")
            prefix = "(思考) " if role == "thought" else ""
            text = _render_blocks(r.get("blocks", []), max_chars=100)
            parts.append(f"- {label}: {prefix}「{text}」(関連度 {r.get('relevance', 0):.2f})")
        for t in reversed(chat_turns[-4:]):
            idx = turns.index(t)
            if idx in shown_indices:
                continue
            shown_indices.add(idx)
            role = t.get("role", "system")
            uid = t.get("user_id", "")
            label = uid or ("User" if role == "user" else "Iris")
            prefix = "(思考) " if role == "thought" else ""
            text = _render_blocks(t.get("blocks", []), max_chars=100)
            parts.append(f"- {label}: {prefix}「{text}」")

    if active_references:
        refs = sorted(active_references, key=len, reverse=True)[:5]
        parts.append("### 参照エンティティ")
        parts.append(", ".join(refs))

    if active_users:
        user_lines = [f"- {nick}" for _, nick in active_users]
        if user_lines:
            parts.append("### 現在の参加者")
            parts.extend(user_lines)

    if not parts:
        return ""
    text = "\n".join(parts)
    if len(text) > max_chars:
        text = text[: max_chars - 3] + "..."
    return text
