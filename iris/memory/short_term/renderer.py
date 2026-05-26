from __future__ import annotations

from collections.abc import Callable

from iris.memory.short_term.models import SearchResult, TurnData


def render_short_term_context(
    turns: list[TurnData],
    active_references: set[str],
    search_fn: Callable[..., list[SearchResult]],
    max_chars: int = 600,
    query: str | None = None,
) -> str:
    if not turns:
        return ""
    parts: list[str] = []

    if query:
        parts.append("### 直近の会話（関連）")
        relevant = search_fn(query, max_results=3)
        shown_indices = {r.get("index", -1) for r in relevant}
        for r in relevant:
            role = r.get("role", "system")
            uid = r.get("user_identity", "")
            label = uid or ("User" if role == "user" else "Iris")
            prefix = "(思考) " if role == "thought" else ""
            parts.append(f"- {label}: {prefix}「{r['content'][:100]}」(関連度 {r.get('relevance', 0):.2f})")
        for t in reversed(turns[-4:]):
            idx = turns.index(t)
            if idx in shown_indices:
                continue
            shown_indices.add(idx)
            role = t.get("role", "system")
            uid = t.get("user_identity", "")
            label = uid or ("User" if role == "user" else "Iris")
            prefix = "(思考) " if role == "thought" else ""
            parts.append(f"- {label}: {prefix}「{t['content'][:100]}」")

    if active_references:
        refs = sorted(active_references, key=len, reverse=True)[:5]
        parts.append("### 参照エンティティ")
        parts.append(", ".join(refs))

    if not parts:
        return ""
    text = "\n".join(parts)
    if len(text) > max_chars:
        text = text[: max_chars - 3] + "..."
    return text
