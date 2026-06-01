"""検索結果のフォーマット統一ヘルパ。

意味検索とベクトル検索で異なる形式の row を `{content, tags, type, score, timestamp}`
に正規化する。新たなフィールド追加の影響範囲を 1 ファイルに閉じる。
"""

from __future__ import annotations

from typing import Any


def format_search_result(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "content": r.get("content", ""),
            "tags": r.get("tags", []),
            "type": r.get("type", "unknown"),
            "score": round(r.get("score", 0.0), 4),
            "timestamp": r.get("timestamp", ""),
        }
        for r in results
    ]


__all__ = ["format_search_result"]
