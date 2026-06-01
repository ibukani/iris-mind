"""PersonaPatchCandidateStore — ペルソナプロファイルへの変更候補を保持する。

自動適用しない。承認されたときだけ ``PersonaPatchPolicy.apply_approved()`` 経由で使う。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from iris.memory.langmem.stores import _IdIndexedJsonlStore
from iris.memory.procedural.persona_patch_models import PersonaPatchCandidate


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
    """承認済みパッチをファイルへ反映する。反映は明示呼び出しのみ。"""

    def __init__(self, store: PersonaPatchCandidateStore) -> None:
        self._store = store

    def apply_approved(
        self,
        item_id: str,
        *,
        backup: bool = True,
    ) -> bool:
        item = self._store.find(item_id)
        if item is None or item.status != "approved":
            return False
        target = Path(item.target_file)
        if backup and target.exists():
            backup_path = target.with_suffix(target.suffix + ".bak")
            backup_path.write_text(target.read_text(encoding="utf-8"), encoding="utf-8")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(item.proposed_patch, encoding="utf-8")
        self._store.update(item_id, status="applied")
        return True


__all__ = ["PersonaPatchCandidateStore", "PersonaPatchPolicy"]
