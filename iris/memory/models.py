from __future__ import annotations

from typing import Any, TypedDict


class ContentBlock(TypedDict, total=False):
    type: str
    text: str
    data: str | None
    mime_type: str | None
    metadata: dict[str, Any] | None


def text_block(text: str) -> ContentBlock:
    return {"type": "text", "text": text}


def blocks_text(blocks: list[ContentBlock]) -> str:
    return "".join(b.get("text", "") for b in blocks if b.get("text"))


def block_tag(block: ContentBlock) -> str:
    t = block.get("type", "text")
    if t == "text":
        return block.get("text", "")
    txt = block.get("text", "")
    mime = block.get("mime_type", "")
    tag = mime or t
    return f"[{tag}] {txt}" if txt else f"[{tag}]"
