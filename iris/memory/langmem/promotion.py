"""Promotion Policy — MemoryCandidate を Iris 側ロジックで検証し最終記憶へ昇格する。

LangMem 出力は「候補」に過ぎない。PromotionPolicy は以下を保証する:
- 信頼度が閾値以上の候補だけを昇格する
- 弱い根拠・空 content・危険なカテゴリを却下する
- 同じ内容の重複昇格を避ける (payload_hash + handler レベル)
- target_store ごとに専用 Handler がディスパッチされる
- relationship / appraisal / persona_patch / style は専用 Handler が保守的に適用
"""

from __future__ import annotations

from typing import Any, Protocol

from loguru import logger

from iris.memory.consolidation.log_store import MemoryConsolidationLogStore
from iris.memory.consolidation.models import MemoryConsolidationRecord
from iris.memory.langmem.handlers import (
    HandlerOutcome,
    PromotionHandler,
)
from iris.memory.langmem.models import MemoryCandidate, TargetStore


class _PromotableStore(Protocol):
    def store_semantic(self, data: Any, room_id: str = "", account_id: str = "") -> None: ...
    def store_episodic(self, data: Any, kind: str = "", room_id: str = "", account_id: str = "") -> None: ...


# 昇格しない / 危険なカテゴリのブロックリスト
_BLOCKED_CATEGORIES: set[str] = {"avoidance"}  # avoidance は evidence 必須、かつ confidence 0.85 以上のみ
_PERSONA_PATCH_MIN_CONFIDENCE = 0.9


class PromotionPolicy:
    """候補→最終記憶の昇格ルール。

    ``handlers`` dict に ``target_store -> PromotionHandler`` を登録する。
    未登録の target_store は ``needs_review`` 扱い。
    """

    def __init__(
        self,
        *,
        long_term: _PromotableStore,
        consolidation_log: MemoryConsolidationLogStore | None = None,
        min_confidence: float = 0.75,
        handlers: dict[TargetStore, PromotionHandler] | None = None,
        duplicate_guard: bool = True,
    ) -> None:
        self._long_term = long_term
        self._log = consolidation_log
        self._min_confidence = min_confidence
        self._handlers: dict[TargetStore, PromotionHandler] = dict(handlers or {})
        self._duplicate_guard = duplicate_guard
        self._seen_hashes: set[str] = set()

    def register_handler(self, target_store: TargetStore, handler: PromotionHandler) -> None:
        """``target_store`` 用の handler を後から登録する。"""
        self._handlers[target_store] = handler

    @property
    def handlers(self) -> dict[TargetStore, PromotionHandler]:
        return dict(self._handlers)

    def promote(
        self,
        candidate: MemoryCandidate,
        room_id: str = "",
        account_id: str = "",
    ) -> tuple[str, str]:
        """候補を 1 件検証して、``(status, reason)`` を返す。status は ``promoted|rejected|needs_review``。"""
        if self._duplicate_guard and self._is_already_seen(candidate):
            self._record_status(candidate, "rejected", "duplicate_payload_hash")
            return "rejected", "duplicate_payload_hash"

        status, reason = self._validate(candidate)
        if status == "promoted":
            try:
                created = self._apply(candidate, room_id=room_id, account_id=account_id)
            except Exception as e:
                logger.warning("PromotionPolicy: apply failed id={} err={}", candidate.id, e)
                status, reason = "rejected", f"apply_failed: {e}"
            else:
                if created is None:
                    status, reason = "rejected", "handler_returned_none"
                elif isinstance(created, HandlerOutcome):
                    status = created.status
                    reason = created.reason or reason
                else:
                    # str の戻り値: 旧来の API。後方互換として promoted 扱い
                    pass
                if status == "promoted":
                    self._remember_hash(candidate)
        self._record_status(candidate, status, reason)
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

    def _is_already_seen(self, c: MemoryCandidate) -> bool:
        if not c.payload_hash:
            return False
        if c.payload_hash in self._seen_hashes:
            return True
        handler = self._handlers.get(c.target_store)
        if handler is not None and getattr(handler, "is_duplicate", None) is not None:
            try:
                if handler.is_duplicate(c):
                    return True
            except Exception:
                logger.warning("PromotionPolicy: handler.is_duplicate raised target_store={}", c.target_store)
        return False

    def _remember_hash(self, c: MemoryCandidate) -> None:
        if c.payload_hash:
            self._seen_hashes.add(c.payload_hash)

    def _record_status(self, c: MemoryCandidate, status: str, reason: str) -> None:
        if status == "rejected":
            c.status = "rejected"
            c.rejection_reason = reason
        elif status == "needs_review":
            c.status = "needs_review"
            c.rejection_reason = reason
        else:
            c.status = "promoted"
            c.rejection_reason = ""

    def _validate(self, c: MemoryCandidate) -> tuple[str, str]:
        if c.target_store not in _SUPPORTED_TARGETS:
            return "needs_review", f"target_store_not_implemented={c.target_store}"

        # persona_patch の confidence gate は handler 側で ``HandlerOutcome`` を返す。
        # ここではデータ構造の妥当性だけを検査する。
        if c.target_store == "persona_patch":
            payload = c.payload or {}
            if not str(payload.get("proposed_patch", "")).strip():
                return "needs_review", "persona_patch_missing_proposed_patch"
            if not str(payload.get("reason", "")).strip():
                return "needs_review", "persona_patch_missing_reason"
            if not c.source_record_ids:
                return "needs_review", "no_source_record_ids"
            return "promoted", ""

        if c.confidence < self._min_confidence:
            return "rejected", f"low_confidence<{self._min_confidence}"

        payload = c.payload or {}
        content = str(payload.get("content", "")).strip()
        if c.target_store not in ("relationship", "appraisal"):
            if not content:
                return "rejected", "empty_content"
            if len(content) < 4:
                return "needs_review", "very_short_content"
        else:
            if c.target_store == "relationship":
                if payload.get("suggested_delta") is None:
                    return "needs_review", "relationship_missing_suggested_delta"
            else:
                if not str(payload.get("trigger_summary", "")).strip():
                    return "needs_review", "appraisal_missing_trigger_summary"

        if not c.source_record_ids:
            return "needs_review", "no_source_record_ids"

        if c.target_store in ("semantic", "episodic", "style"):
            evidence = str(payload.get("evidence", "")).strip()
            if not evidence:
                return "needs_review", "missing_evidence"

        if c.target_store in ("semantic", "episodic"):
            for keyword in _SENSITIVE_KEYWORDS:
                if keyword in content and c.confidence < 0.9:
                    return "rejected", f"sensitive_keyword={keyword}"
            if payload.get("category") in _BLOCKED_CATEGORIES and c.confidence < 0.85:
                return "rejected", "avoidance_requires_high_confidence"

        return "promoted", ""

    def _apply(
        self,
        c: MemoryCandidate,
        *,
        room_id: str,
        account_id: str,
    ) -> str | None:
        if c.target_store == "semantic":
            return self._promote_semantic(c, room_id=room_id, account_id=account_id)
        if c.target_store == "episodic":
            return self._promote_episodic(c, room_id=room_id, account_id=account_id)
        handler = self._handlers.get(c.target_store)
        if handler is None:
            raise ValueError(f"no handler for {c.target_store}")
        return handler.apply(c, room_id=room_id, account_id=account_id)

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
