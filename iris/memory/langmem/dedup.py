"""MemoryCandidate の重複検出用ハッシュ計算と正規化ヘルパ。

責務:
- 同じ内容 (target_store + 正規化 payload + scope) を持つ候補を同一とみなす
- 一時的なフィールド (id, created_at, updated_at, retry_count, status, timestamp 系の metadata) は除外
- 文字列フィールドは trim して空白差を吸収
- JSON は ``orjson`` の SORT_KEYS オプションでキーの順序を吸収
- 出力は ``sha256`` の16進文字列 (再現性重視、衝突確率は十分小さい)
"""

from __future__ import annotations

import hashlib
from typing import Any

import orjson

_VOLATILE_TOP_LEVEL_KEYS: frozenset[str] = frozenset(
    {
        "id",
        "created_at",
        "updated_at",
        "timestamp",
        "retry_count",
        "status",
        "rejection_reason",
    }
)
_VOLATILE_METADATA_KEYS: frozenset[str] = frozenset(
    {
        "id",
        "created_at",
        "updated_at",
        "timestamp",
        "retry_count",
    }
)

# スコープ正規化に含める候補ペイロードのキー。
# 値そのものではなく存在を評価対象にし、値が違うとハッシュが変わる。
_SCOPE_PAYLOAD_KEYS: tuple[str, ...] = (
    "category",
    "kind",
    "scope",
    "signal",
    "appraisal_dimension",
)


def normalize_string(value: Any) -> str:
    """文字列をトリムした形に正規化する。"""
    if value is None:
        return ""
    if not isinstance(value, str):
        return str(value).strip()
    return value.strip()


def _strip_volatile(value: Any) -> Any:
    """dict 内の揮発フィールドを取り除く。再帰はしない (payload は単純な構造想定)。"""
    if not isinstance(value, dict):
        return value
    return {k: v for k, v in value.items() if k not in _VOLATILE_TOP_LEVEL_KEYS}


def _normalize_strings_in_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """payload 内の ``content`` / ``evidence`` / ``reason`` などを trim する。"""
    keys_to_trim = ("content", "evidence", "reason", "trigger_summary", "proposed_patch", "lesson")
    out: dict[str, Any] = {}
    for k, v in payload.items():
        if k in keys_to_trim and isinstance(v, str):
            out[k] = v.strip()
        else:
            out[k] = v
    return out


def _normalize_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    if not metadata:
        return {}
    return {k: v for k, v in metadata.items() if k not in _VOLATILE_METADATA_KEYS}


def compute_payload_signature(payload: dict[str, Any]) -> str:
    """payload だけから決まる正規化済み署名 (キー順非依存、空白非依存)。"""
    cleaned = _strip_volatile(payload or {})
    cleaned = _normalize_strings_in_payload(cleaned)
    encoded = orjson.dumps(cleaned, option=orjson.OPT_SORT_KEYS)
    return hashlib.sha256(encoded).hexdigest()


def compute_candidate_hash(
    *,
    target_store: str,
    payload: dict[str, Any],
    account_id: str = "",
    room_id: str = "",
) -> str:
    """候補全体の重複検出用ハッシュを計算する。

    構成要素:
    - target_store (正規化)
    - 正規化済み payload
    - account_id / room_id (空文字は同一扱い)
    """
    payload_sig = compute_payload_signature(payload or {})
    blob = {
        "target_store": str(target_store or "").strip(),
        "account_id": str(account_id or "").strip(),
        "room_id": str(room_id or "").strip(),
        "payload_sig": payload_sig,
    }
    encoded = orjson.dumps(blob, option=orjson.OPT_SORT_KEYS)
    return hashlib.sha256(encoded).hexdigest()


__all__ = [
    "compute_candidate_hash",
    "compute_payload_signature",
    "normalize_string",
]
