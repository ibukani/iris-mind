"""Room フィールド更新時の値検証 (state の文字列→Enum 変換、metadata の dict 検証)。

`RoomManager.update_room` のループから呼び出される純粋関数。
"""

from __future__ import annotations

from typing import Any

from iris.room.models import Room, RoomState


def coerce_update_field(room: Room, key: str, value: Any) -> tuple[Any, Any]:
    """`room.<key>` に代入して良い値に正規化し、古い値と新しい値を返す。"""
    if key not in {"name", "description", "topic", "state", "created_by", "metadata"}:
        raise ValueError(f"unknown room field: {key}")

    if key == "state":
        if isinstance(value, RoomState):
            new_value: Any = value
        elif isinstance(value, str):
            new_value = RoomState(value)
        else:
            raise ValueError(f"invalid room state: {value!r}")
    elif key == "metadata":
        new_value = value
        if not isinstance(value, dict):
            raise ValueError("metadata must be an object")
    else:
        new_value = value
        if not isinstance(value, str):
            raise ValueError(f"{key} must be a string")

    return getattr(room, key, None), new_value


__all__ = ["coerce_update_field"]
