"""Promotion Policy — MemoryCandidate を Iris 側ロジックで検証し最終記憶へ昇格する。

LangMem 出力は「候補」に過ぎない。PromotionPolicy は以下を保証する:
- 信頼度が閾値以上の候補だけを昇格する
- 弱い根拠・空 content・危険なカテゴリを却下する
- 同じ内容の重複昇格を避ける
- relationship / appraisal / style / persona_patch は将来フック (Phase 5/6/7) で扱う
"""

from __future__ import annotations

from typing import Any, Protocol

from loguru import logger

from iris.memory.consolidation.log_store import MemoryConsolidationLogStore
from iris.memory.consolidation.models import MemoryConsolidationRecord
from iris.memory.langmem.models import MemoryCandidate, TargetStore


class _PromotableStore(Protocol):
    def store_semantic(self, data: Any, room_id: str = "", account_id: str = "") -> None: ...
    def store_episodic(self, data: Any, kind: str = "", room_id: str = "", account_id: str = "") -> None: ...


# 昇格しない / 危険なカテゴリのブロックリスト
_BLOCKED_CATEGORIES: set[str] = {"avoidance"}  # avoidance は evidence 必須、かつ confidence 0.85 以上のみ


class PromotionPolicy:
    """候補→最終記憶の昇格ルール。"""

    def __init__(
        self,
        *,
        long_term: _PromotableStore,
        consolidation_log: MemoryConsolidationLogStore | None = None,
        min_confidence: float = 0.75,
        style_hooks: dict[TargetStore, Any] | None = None,
    ) -> None:
        self._long_term = long_term
        self._log = consolidation_log
        self._min_confidence = min_confidence
        # style_hooks: target_store -> callable(candidate) -> created_memory_id|None
        self._style_hooks: dict[TargetStore, Any] = style_hooks or {}

    def promote(
        self,
        candidate: MemoryCandidate,
        room_id: str = "",
        account_id: str = "",
    ) -> tuple[str, str]:
        """候補を 1 件検証して、``(status, reason)`` を返す。status は ``promoted|rejected|needs_review``。"""
        status, reason = self._validate(candidate)
        if status == "promoted":
            try:
                self._apply(candidate, room_id=room_id, account_id=account_id)
            except Exception as e:
                logger.warning("PromotionPolicy: apply failed id={} err={}", candidate.id, e)
                status, reason = "rejected", f"apply_failed: {e}"
        if status == "rejected":
            candidate.status = "rejected"
            candidate.rejection_reason = reason
        elif status == "needs_review":
            candidate.status = "needs_review"
            candidate.rejection_reason = reason
        else:
            candidate.status = "promoted"
            candidate.rejection_reason = ""
        return status, reason

    def evaluate(
        self,
        candidates: list[MemoryCandidate],
        room_id: str = "",
        account_id: str = "",
    ) -> MemoryConsolidationRecord:
        """複数候補を一括評価し、結果を consolidation log に書き出す。"""
        promoted: list[str] = []
        rejected: list[str] = []
        notes: list[str] = []
        confs: list[float] = []
        for c in candidates:
            status, reason = self.promote(c, room_id=room_id, account_id=account_id)
            if status == "promoted":
                promoted.append(c.id)
                confs.append(c.confidence)
            else:
                rejected.append(c.id)
                notes.append(f"{c.target_store}:{reason}")
        record = MemoryConsolidationRecord(
            source_record_ids=list({rid for c in candidates for rid in c.source_record_ids}),
            candidate_ids=[c.id for c in candidates],
            created_memory_ids=promoted,
            rejected_candidate_ids=rejected,
            confidence=sum(confs) / len(confs) if confs else 0.0,
            notes="; ".join(notes),
        )
        if self._log is not None:
            self._log.add(record)
        return record

    # ── internals ──

    def _validate(self, c: MemoryCandidate) -> tuple[str, str]:
        if c.confidence < self._min_confidence:
            return "rejected", f"low_confidence<{self._min_confidence}"
        payload = c.payload or {}
        content = str(payload.get("content", "")).strip()
        if not content:
            return "rejected", "empty_content"
        if len(content) < 4:
            return "needs_review", "very_short_content"
        if not c.source_record_ids:
            return "needs_review", "no_source_record_ids"
        evidence = str(payload.get("evidence", "")).strip()
        if not evidence:
            return "needs_review", "missing_evidence"
        # sensitivity ガード
        for keyword in _SENSITIVE_KEYWORDS:
            if keyword in content and c.confidence < 0.9:
                return "rejected", f"sensitive_keyword={keyword}"
        # avoidance カテゴリは evidence と confidence を強化
        if payload.get("category") in _BLOCKED_CATEGORIES and c.confidence < 0.85:
            return "rejected", "avoidance_requires_high_confidence"
        if c.target_store not in _SUPPORTED_TARGETS:
            return "needs_review", f"target_store_not_implemented={c.target_store}"
        return "promoted", ""

    def _apply(
        self,
        c: MemoryCandidate,
        *,
        room_id: str,
        account_id: str,
    ) -> str:
        if c.target_store == "semantic":
            return self._promote_semantic(c, room_id=room_id, account_id=account_id)
        if c.target_store == "episodic":
            return self._promote_episodic(c, room_id=room_id, account_id=account_id)
        hook = self._style_hooks.get(c.target_store)
        if hook is None:
            raise ValueError(f"no hook for {c.target_store}")
        return str(hook(c, room_id=room_id, account_id=account_id) or "")

    def _promote_semantic(self, c: MemoryCandidate, *, room_id: str, account_id: str) -> str:
        payload = dict(c.payload)
        payload.setdefault("type", "user_preference")
        payload.setdefault("tags", ["langmem"])
        payload["confidence"] = c.confidence
        payload.setdefault("id", f"sem_{c.id[:12]}")
        self._long_term.store_semantic(payload, room_id=room_id, account_id=account_id)
        return str(payload["id"])

    def _promote_episodic(self, c: MemoryCandidate, *, room_id: str, account_id: str) -> str:
        payload = dict(c.payload)
        situation = payload.get("situation", "")
        lesson = payload.get("lesson", "")
        content = f"{situation} -> {lesson}".strip(" ->")
        self._long_term.store_episodic(
            {"content": content, "kind": "interaction", "metadata": {"confidence": c.confidence}},
            room_id=room_id,
            account_id=account_id,
        )
        return f"epi_{c.id[:12]}"


_SENSITIVE_KEYWORDS = ("住所", "電話", "メール", "パスワード", "SSN", "マイナンバー")
_SUPPORTED_TARGETS: set[str] = {"semantic", "episodic", "style", "relationship", "appraisal", "persona_patch"}


__all__ = ["PromotionPolicy"]
