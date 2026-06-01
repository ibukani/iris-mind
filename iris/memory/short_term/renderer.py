from __future__ import annotations

from iris.memory.models import ContentBlock, block_tag
from iris.memory.short_term.models import ActiveUser, ShortTermSearchResult, ShortTermTurn


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
    turns: list[ShortTermTurn],
    active_references: set[str],
    relevant_results: list[ShortTermSearchResult] | None = None,
    max_chars: int = 600,
    active_users: list[ActiveUser] | None = None,
    room_id: str = "",
) -> str:
    """LLM向け短期記憶コンテキストを整形する（純粋関数、検索は呼び出し元で解決済み）。"""
    if not turns:
        return ""
    if room_id:
        turns = [t for t in turns if t.get("room_id", "") == room_id]
    parts: list[str] = []

    chat_turns = [t for t in turns if t.get("role") not in ("system",)]
    if not chat_turns and not relevant_results:
        if active_users:
            user_lines = [f"- {u.display_name}" for u in active_users]
            parts.append("### 現在の参加者")
            parts.extend(user_lines)
            text = "\n".join(parts)
            if len(text) > max_chars:
                text = text[: max_chars - 3] + "..."
            return text
        return ""

    if relevant_results:
        parts.append("### 直近の会話（関連）")
        shown_ids: set[int] = set()
        for r in relevant_results:
            shown_ids.add(id(r))
            role = r.get("role", "system")
            uid = r.get("account_id", "")
            label = uid or ("User" if role == "user" else "Iris")
            prefix = "(思考) " if role == "thought" else ""
            text = _render_blocks(r.get("blocks", []), max_chars=100)
            parts.append(f"- {label}: {prefix}「{text}」(関連度 {r.get('relevance', 0):.2f})")
        for t in reversed(chat_turns[-4:]):
            if id(t) in shown_ids:
                continue
            role = t.get("role", "system")
            uid = t.get("account_id", "")
            label = uid or ("User" if role == "user" else "Iris")
            prefix = "(思考) " if role == "thought" else ""
            text = _render_blocks(t.get("blocks", []), max_chars=100)
            parts.append(f"- {label}: {prefix}「{text}」")

    if active_references:
        refs = sorted(active_references, key=len, reverse=True)[:5]
        parts.append("### 参照エンティティ")
        parts.append(", ".join(refs))

    if active_users:
        user_lines = [f"- {u.display_name}" for u in active_users]
        if user_lines:
            parts.append("### 現在の参加者")
            parts.extend(user_lines)

    if not parts:
        return ""
    text = "\n".join(parts)
    if len(text) > max_chars:
        text = text[: max_chars - 3] + "..."
    return text
