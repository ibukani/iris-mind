"""Archive policy — ArchiveStore 動作設定の Pydantic モデル。"""

from __future__ import annotations

from pydantic import BaseModel


class ArchivePolicy(BaseModel):
    """Archive への書き込み・読み出しポリシ。"""

    enabled: bool = True
    archive_dir: str = ".iris/data/conversations"
    max_per_file_bytes: int = 4_000_000
    keep_recent_files: int = 30


__all__ = ["ArchivePolicy"]
