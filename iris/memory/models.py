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


def system_event_block(
    text: str,
    *,
    event_type: str,
    account_id: str = "",
    display_name: str = "",
    room_id: str = "",
) -> ContentBlock:
    return {
        "type": "system_event",
        "text": text,
        "metadata": {
            "event_type": event_type,
            "account_id": account_id,
            "display_name": display_name,
            "room_id": room_id,
        },
    }


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
