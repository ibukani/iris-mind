"""PersonaPatchCandidateStore — ペルソナプロファイルへの変更候補を保持する。

自動適用しない。承認されたときだけ ``PersonaPatchPolicy.apply_approved()`` 経由で使う。
"""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from loguru import logger

from iris.memory.langmem.stores import _IdIndexedJsonlStore
from iris.memory.procedural.persona_patch_models import PersonaPatchCandidate

# iris_profile.md 配下に存在してよいファイルだけを許可する。
# 任意の絶対パスを書かれると /etc/passwd 等を破壊できるため、相対パスとして扱い
# ``.iris/config/`` 配下を強制する。
_PROFILE_DIR = Path(".iris/config")
_PROFILE_GLOB = re.compile(r"^\.iris/config/[A-Za-z0-9_./-]+\.md$")

_SECTION_HEADER = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


def _resolve_target_path(target_file: str, base: Path) -> Path:
    """``target_file`` を base からの相対パスに正規化し、``.iris/config/`` 配下であることを保証する。

    絶対パス・``..`` を含むパスを拒否する (``resolve()`` 後のパスが
    ``base/.iris/config/`` 配下であることを厳格に検証する)。
    """
    raw = (target_file or "").strip()
    if not raw:
        return base / _PROFILE_DIR / "iris_profile.md"
    candidate = Path(raw)
    if candidate.is_absolute():
        raise ValueError(f"absolute target_file is not allowed: {target_file}")
    parts = candidate.parts
    if not parts or parts[0] != ".iris":
        raise ValueError(f"target_file must be under .iris/: {target_file}")
    if ".." in parts:
        raise ValueError(f"target_file must not contain '..': {target_file}")
    if not _PROFILE_GLOB.match(str(candidate)):
        raise ValueError(f"target_file must match .iris/config/**/*.md (got: {target_file})")
    resolved = (base / candidate).resolve()
    profile_root = (base / _PROFILE_DIR).resolve()
    try:
        resolved.relative_to(profile_root)
    except ValueError as e:
        raise ValueError(f"target_file resolves outside .iris/config/: {target_file}") from e
    return resolved


class PersonaPatchCandidateStore(_IdIndexedJsonlStore[PersonaPatchCandidate]):
    def __init__(self, path: str) -> None:
        super().__init__(path, PersonaPatchCandidate)

    def list_pending(self) -> list[PersonaPatchCandidate]:
        return self.list_filtered(status="pending")

    def approve(self, item_id: str) -> PersonaPatchCandidate | None:
        return self.update(item_id, status="approved")

    def reject(self, item_id: str, reason: str = "") -> PersonaPatchCandidate | None:
        meta: dict[str, Any] = {"rejection_reason": reason}
        return self.update(item_id, status="rejected", metadata=meta)


class PersonaPatchPolicy:
    """承認済みパッチをファイルへ反映する。反映は明示呼び出しのみ。

    安全策:
    - ``target_file`` は ``.iris/config/**/*.md`` 配下に限定 (絶対パス・親参照を拒否)
    - 既定では **append モード**: 既存セクションを壊さず ``proposed_patch`` を末尾に追加
    - ``replace=True`` を明示した時だけファイル全置換 (要バックアップ)
    """

    def __init__(
        self,
        store: PersonaPatchCandidateStore,
        *,
        base_dir: str | Path | None = None,
    ) -> None:
        self._store = store
        self._base = Path(base_dir) if base_dir is not None else Path.cwd()

    def apply_approved(
        self,
        item_id: str,
        *,
        backup: bool = True,
        replace: bool = False,
    ) -> bool:
        item = self._store.find(item_id)
        if item is None or item.status != "approved":
            return False
        try:
            target = _resolve_target_path(item.target_file, self._base)
        except ValueError as e:
            logger.error("PersonaPatchPolicy: unsafe target_file rejected item={} err={}", item_id, e)
            return False

        if not item.proposed_patch.strip():
            logger.warning("PersonaPatchPolicy: empty proposed_patch item={}", item_id)
            return False

        target.parent.mkdir(parents=True, exist_ok=True)

        if backup and target.exists():
            backup_path = target.with_suffix(target.suffix + ".bak")
            backup_path.write_text(target.read_text(encoding="utf-8"), encoding="utf-8")

        if replace or not target.exists():
            target.write_text(item.proposed_patch, encoding="utf-8")
        else:
            existing = target.read_text(encoding="utf-8")
            if not existing.endswith("\n"):
                existing += "\n"
            separator = "" if not existing.rstrip() else "\n"
            target.write_text(
                existing + separator + item.proposed_patch.rstrip("\n") + "\n",
                encoding="utf-8",
            )

        self._store.update(item_id, status="applied")
        return True


__all__ = ["PersonaPatchCandidateStore", "PersonaPatchPolicy"]
