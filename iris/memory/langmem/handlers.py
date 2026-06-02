"""Promotion Handlers — MemoryCandidate を各ストア固有ロジックで昇格する責務分離クラス群。

責務:
- ``PromotionPolicy`` から target_store ごとにディスパッチされる
- relationship / appraisal / persona_patch はアイソレートされた保守的ロジックを持つ
- LangMem は candidate を生成するだけで、handler を通さずに state を変更することは禁止
- すべての delta / patch は confidence と scope に基づいてクランプされる
- すべての変更は ``source_record_ids`` と consolidation log に必ず記録される
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, cast

from loguru import logger

from iris.limbic.relationship import RelationshipManager
from iris.limbic.stores.appraisal_store import AppraisalEpisodeStore
from iris.limbic.stores.relationship_store import RelationshipStateStore
from iris.memory.langmem.models import MemoryCandidate, TargetStore
from iris.memory.procedural.models import StyleKind, StyleMemory, StyleScope
from iris.memory.procedural.persona_patch_store import PersonaPatchCandidateStore, PersonaPatchPolicy
from iris.memory.procedural.style_store import StyleMemoryStore


class PromotionHandler(Protocol):
    """target_store ごとの昇格処理プロトコル。"""

    target_store: TargetStore

    def apply(
        self,
        candidate: MemoryCandidate,
        *,
        room_id: str = "",
        account_id: str = "",
    ) -> str | None:
        """候補を実際のストアに反映し、作成されたエンティティ ID を返す。"""
        ...

    def is_duplicate(self, candidate: MemoryCandidate) -> bool:
        """既に同等のものが存在する場合 True。"""
        ...


# ───────── 共通ヘルパ ─────────

# 1 候補あたりが動かして良い delta の絶対上限 (relationship.trust/familiarity)
_MAX_RELATIONSHIP_DELTA = 0.05
# 負方向はより厳しく (信頼低下は回復しづらいため)
_NEGATIVE_RELATIONSHIP_RATIO = 0.5

# 1 候補あたりが動かして良い appraisal delta の絶対上限
_MAX_APPRAISAL_DELTA = 0.5

# persona_patch は personality を変えるのでより高い confidence が必要
_PERSONA_PATCH_MIN_CONFIDENCE = 0.9


def _clamp_delta(value: float, max_abs: float) -> float:
    if value > max_abs:
        return max_abs
    if value < -max_abs:
        return -max_abs
    return value


def _scale_by_confidence(value: float, confidence: float) -> float:
    """delta を confidence でスケールし、|delta| が単調増加しないようにする。"""
    c = max(0.0, min(1.0, confidence))
    return value * c


_STYLE_KINDS: frozenset[str] = frozenset(
    {
        "tone_preference",
        "successful_pattern",
        "running_gag",
        "avoidance_rule",
        "chaos_preference",
        "conversation_strategy",
    }
)
_STYLE_SCOPES: frozenset[str] = frozenset({"global", "account", "room"})


# ───────── RelationshipPromotionHandler ─────────


class RelationshipPromotionHandler:
    """``target_store='relationship'`` の候補を RelationshipManager に適用する。

    ルール:
    - 信頼度 < 0.6 は無視
    - ``suggested_delta`` の絶対値は ``_MAX_RELATIONSHIP_DELTA`` を超えない
    - 負方向は正方向の ``_NEGATIVE_RELATIONSHIP_RATIO`` 倍までしかクランプしない
      (信頼低下のダメージを抑える)
    - confidence でさらにスケールする
    - 変更は RelationshipStateStore に保存される
    """

    target_store: TargetStore = "relationship"
    min_confidence: float = 0.6
    max_delta: float = _MAX_RELATIONSHIP_DELTA
    negative_ratio: float = _NEGATIVE_RELATIONSHIP_RATIO

    def __init__(
        self,
        *,
        relationship_manager: RelationshipManager,
        snapshot_store: RelationshipStateStore | None = None,
    ) -> None:
        self._manager = relationship_manager
        self._snapshots = snapshot_store

    def apply(
        self,
        candidate: MemoryCandidate,
        *,
        room_id: str = "",
        account_id: str = "",
    ) -> str | None:
        if candidate.confidence < self.min_confidence:
            logger.debug(
                "RelationshipPromotionHandler: skip low confidence id={} conf={}",
                candidate.id,
                candidate.confidence,
            )
            return None
        payload = candidate.payload or {}
        suggested = float(payload.get("suggested_delta", 0.0) or 0.0)
        if suggested == 0.0:
            return None
        field = str(payload.get("field", "trust") or "trust")
        if field not in ("trust", "familiarity"):
            field = "trust"

        abs_cap = self.max_delta
        if suggested < 0:
            abs_cap = self.max_delta * self.negative_ratio
        clamped = _clamp_delta(suggested, abs_cap)
        scaled = _scale_by_confidence(clamped, candidate.confidence)

        before = self._manager.get_state(account_id=account_id)
        new_state = self._manager.apply_candidate_delta(
            field=field,
            delta=scaled,
            account_id=account_id,
        )
        if self._snapshots is not None:
            self._snapshots.save_snapshot(account_id, new_state, room_id=room_id)
        logger.info(
            "RelationshipPromotionHandler: account={} field={} delta={:.4f} conf={:.2f} before.trust={:.3f} after.trust={:.3f}",
            account_id,
            field,
            scaled,
            candidate.confidence,
            before.trust,
            new_state.trust,
        )
        return f"rel_{candidate.id[:12]}"

    def is_duplicate(self, candidate: MemoryCandidate) -> bool:
        # 関係性 delta は時間とともに減衰しないので、同じ confidence + delta の
        # 連続 candidate は PromotionPolicy 側で重複検出する想定。
        # handler レベルでは重複とみなさない (policy 層の payload_hash ガードで吸収する)
        return False


# ───────── AppraisalPromotionHandler ─────────


class AppraisalPromotionHandler:
    """``target_store='appraisal'`` の候補を AppraisalEpisodeStore にエピソードとして記録する。

    重要: 実際の ``Appraiser`` / ``Mood`` / 関係性 live state は変更しない。
    LangMem の appraisal 出力は「参考エピソード」としてのみ保存され、
    本体の appraisal 計算は Iris 側ロジックで継続する。
    """

    target_store: TargetStore = "appraisal"
    min_confidence: float = 0.5
    max_delta: float = _MAX_APPRAISAL_DELTA

    def __init__(
        self,
        *,
        episode_store: AppraisalEpisodeStore,
    ) -> None:
        self._episodes = episode_store

    def apply(
        self,
        candidate: MemoryCandidate,
        *,
        room_id: str = "",
        account_id: str = "",
    ) -> str | None:
        if candidate.confidence < self.min_confidence:
            logger.debug(
                "AppraisalPromotionHandler: skip low confidence id={} conf={}",
                candidate.id,
                candidate.confidence,
            )
            return None
        payload = candidate.payload or {}
        estimated = float(payload.get("estimated_delta", 0.0) or 0.0)
        clamped = _clamp_delta(estimated, self.max_delta)
        scaled = _scale_by_confidence(clamped, candidate.confidence)

        from iris.limbic.models import Mood
        from iris.limbic.stores.appraisal_store import AppraisalEpisode

        episode = AppraisalEpisode(
            account_id=account_id,
            room_id=room_id,
            trigger_summary=str(payload.get("trigger_summary", "")).strip(),
            context_type=str(payload.get("appraisal_dimension", "general")),
            appraisal={
                "dimension": str(payload.get("appraisal_dimension", "")),
                "estimated_delta_raw": estimated,
                "estimated_delta_clamped": scaled,
                "reason": str(payload.get("reason", "")),
                "source": "langmem_candidate",
                "source_candidate_id": candidate.id,
                "source_record_ids": list(candidate.source_record_ids),
            },
            mood=Mood(),
            reappraisal_needed=False,
            reappraisal_suggestion="",
        )
        self._episodes.add(episode)
        logger.info(
            "AppraisalPromotionHandler: recorded episode id={} dim={} delta={:.3f} conf={:.2f}",
            episode.id,
            payload.get("appraisal_dimension"),
            scaled,
            candidate.confidence,
        )
        return episode.id

    def is_duplicate(self, candidate: MemoryCandidate) -> bool:
        return False


# ───────── PersonaPatchPromotionHandler ─────────


class PersonaPatchPromotionHandler:
    """``target_store='persona_patch'`` の候補を ``PersonaPatchCandidateStore`` に書き込む。

    重要:
    - 自動適用しない。承認フローでしか適用されない。
    - ``PersonaPatchPolicy.apply_approved()`` だけがファイル書き込みを行う。
    - confidence 不足でも ``needs_review=True / low_confidence=True`` メタデータを
      付けた pending エントリとして保存し、ユーザが後で見られるようにする。
    """

    target_store: TargetStore = "persona_patch"
    min_confidence: float = _PERSONA_PATCH_MIN_CONFIDENCE

    def __init__(
        self,
        *,
        store: PersonaPatchCandidateStore,
        policy: PersonaPatchPolicy | None = None,
    ) -> None:
        self._store = store
        self._policy = policy or PersonaPatchPolicy(store)

    def apply(
        self,
        candidate: MemoryCandidate,
        *,
        room_id: str = "",
        account_id: str = "",
    ) -> HandlerOutcome:
        payload = candidate.payload or {}
        proposed = str(payload.get("proposed_patch", "")).strip()
        reason = str(payload.get("reason", "")).strip()
        target_file = str(payload.get("target_file", ".iris/config/iris_profile.md") or "")
        evidence = str(payload.get("evidence", "")).strip()

        if not proposed or not reason:
            logger.warning(
                "PersonaPatchPromotionHandler: missing required fields id={} reason={} patch_len={}",
                candidate.id,
                bool(reason),
                len(proposed),
            )
            return HandlerOutcome.rejected("missing_required_fields")

        from iris.memory.procedural.persona_patch_models import PersonaPatchCandidate

        if candidate.confidence < self.min_confidence:
            pending = PersonaPatchCandidate(
                reason=reason,
                proposed_patch=proposed,
                target_file=target_file,
                evidence_record_ids=list(candidate.source_record_ids),
                confidence=candidate.confidence,
                status="pending",
                metadata={
                    "needs_review": True,
                    "low_confidence": True,
                    "source_candidate_id": candidate.id,
                    "evidence": evidence,
                },
            )
            self._store.add(pending)
            logger.info(
                "PersonaPatchPromotionHandler: needs_review low confidence id={} conf={:.2f}",
                candidate.id,
                candidate.confidence,
            )
            return HandlerOutcome.needs_review(pending.id, "low_confidence_pending")

        item = PersonaPatchCandidate(
            reason=reason,
            proposed_patch=proposed,
            target_file=target_file,
            evidence_record_ids=list(candidate.source_record_ids),
            confidence=candidate.confidence,
            status="pending",
            metadata={
                "source_candidate_id": candidate.id,
                "evidence": evidence,
            },
        )
        self._store.add(item)
        logger.info(
            "PersonaPatchPromotionHandler: pending proposal created id={} target={} conf={:.2f}",
            item.id,
            target_file,
            candidate.confidence,
        )
        return HandlerOutcome.promoted(item.id)

    def is_duplicate(self, candidate: MemoryCandidate) -> bool:
        payload = candidate.payload or {}
        for existing in self._store.list_pending():
            if (
                existing.reason == str(payload.get("reason", "")).strip()
                and existing.proposed_patch == str(payload.get("proposed_patch", "")).strip()
                and existing.target_file == str(payload.get("target_file", ".iris/config/iris_profile.md"))
            ):
                return True
        return False


@dataclass(frozen=True)
class HandlerOutcome:
    """Promotion handler の戻り値。status / reason / memory_id を表現する。"""

    status: str  # "promoted" | "needs_review" | "rejected"
    reason: str = ""
    memory_id: str = ""

    @classmethod
    def promoted(cls, memory_id: str = "") -> HandlerOutcome:
        return cls(status="promoted", reason="", memory_id=memory_id)

    @classmethod
    def needs_review(cls, memory_id: str, reason: str) -> HandlerOutcome:
        return cls(status="needs_review", reason=reason, memory_id=memory_id)

    @classmethod
    def rejected(cls, reason: str) -> HandlerOutcome:
        return cls(status="rejected", reason=reason, memory_id="")


# ───────── StylePromotionHandler ─────────


class StylePromotionHandler:
    """``target_store='style'`` の候補を ``StyleMemoryStore`` に書き込む。"""

    target_store: TargetStore = "style"
    min_confidence: float = 0.6

    def __init__(self, *, style_store: StyleMemoryStore) -> None:
        self._store = style_store

    def apply(
        self,
        candidate: MemoryCandidate,
        *,
        room_id: str = "",
        account_id: str = "",
    ) -> str | None:
        if candidate.confidence < self.min_confidence:
            return None
        payload = dict(candidate.payload)
        kind_value = str(payload.get("kind", "successful_pattern"))
        scope_value = str(payload.get("scope", "account") or "account")
        item = StyleMemory(
            kind=cast(StyleKind, kind_value if kind_value in _STYLE_KINDS else "successful_pattern"),
            content=str(payload.get("content", "")).strip(),
            evidence=str(payload.get("evidence", "")).strip(),
            confidence=candidate.confidence,
            scope=cast(StyleScope, scope_value if scope_value in _STYLE_SCOPES else "account"),
            account_id=account_id,
            room_id=room_id,
            activation_condition=str(payload.get("activation_condition", "")).strip(),
            source_record_ids=list(candidate.source_record_ids),
        )
        if not item.content:
            return None
        self._store.add(item)
        logger.info(
            "StylePromotionHandler: added style memory id={} kind={} scope={}",
            item.id,
            item.kind,
            item.scope,
        )
        return item.id

    def is_duplicate(self, candidate: MemoryCandidate) -> bool:
        content = str((candidate.payload or {}).get("content", "")).strip()
        if not content:
            return False
        for existing in self._store.list_all():
            if existing.content == content and existing.kind == str((candidate.payload or {}).get("kind", "")):
                return True
        return False


__all__ = [
    "AppraisalPromotionHandler",
    "PersonaPatchPromotionHandler",
    "PromotionHandler",
    "RelationshipPromotionHandler",
    "StylePromotionHandler",
]
