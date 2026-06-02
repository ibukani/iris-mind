"""MemoryPipeline — LangMem 抽出→PromotionPolicy→最終記憶の統合フローを管理する。

責務:
- 短期記憶 / 短期 turns を見て、``batch_min_turns`` を超えたら抽出ジョブを作成
- 抽出ジョブを ``LangMemExtractor`` で実行し候補を生成
- 候補を ``PromotionPolicy`` で昇格
- 失敗は握り潰してログに記録し、メイン会話フローを止めない
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from iris.kernel.config import LangMemConfig, MemoryConfig
from iris.memory.archive.store import RawConversationArchiveStore
from iris.memory.consolidation.log_store import MemoryConsolidationLogStore
from iris.memory.langmem.extractor import LangMemExtractor, make_job_scope_resolver
from iris.memory.langmem.models import MemoryExtractionJob, PassType
from iris.memory.langmem.promotion import PromotionPolicy
from iris.memory.langmem.stores import MemoryExtractionJobStore


class MemoryPipeline:
    """LangMem ベースの長期記憶抽出パイプライン。"""

    def __init__(
        self,
        *,
        config: LangMemConfig,
        memory_config: MemoryConfig,
        archive: RawConversationArchiveStore,
        job_store: MemoryExtractionJobStore,
        candidate_store: Any,
        extractor: LangMemExtractor,
        promotion_policy: PromotionPolicy,
        consolidation_log: MemoryConsolidationLogStore | None = None,
    ) -> None:
        self._config = config
        self._memory_config = memory_config
        self._archive = archive
        self._job_store = job_store
        self._candidate_store = candidate_store
        self._extractor = extractor
        self._promotion = promotion_policy
        self._log = consolidation_log

    @property
    def enabled(self) -> bool:
        return self._config.enabled

    def run_pass(
        self,
        pass_type: PassType,
        *,
        source_record_ids: list[str] | None = None,
        account_id: str = "",
        room_id: str = "",
    ) -> list[Any]:
        """``pass_type`` の抽出ジョブを 1 件作成・実行し、生成された候補のリストを返す。"""
        if not self.enabled:
            return []
        record_ids, records = self._collect_records(source_record_ids)
        if not records:
            return []
        job = MemoryExtractionJob(
            source_record_ids=record_ids,
            pass_type=pass_type,
            model=self._config.model_role,
            account_id=account_id,
            room_id=room_id,
        )
        self._job_store.add(job)
        self._job_store.update(job.id, status="running")
        try:
            # Job のスコープを resolver として明示注入する。
            # 候補生成時に account_id/room_id を欠落させないため、
            # デフォルト resolver の空文字フォールバックに依存しない。
            candidates = self._extractor.run(
                job,
                records,
                scope_resolver=make_job_scope_resolver(account_id, room_id),
            )
        except Exception as e:
            logger.warning("MemoryPipeline: extractor crashed pass={} err={}", pass_type, e)
            self._job_store.update(job.id, status="failed", error=str(e))
            return []
        try:
            self._promotion.evaluate(
                candidates,
                room_id=room_id,
                account_id=account_id,
            )
        except Exception as e:
            logger.warning("MemoryPipeline: promotion crashed pass={} err={}", pass_type, e)
        self._job_store.update(job.id, status="succeeded")
        return candidates

    def run_full_cycle(
        self,
        *,
        source_record_ids: list[str] | None = None,
        account_id: str = "",
        room_id: str = "",
    ) -> dict[PassType, list[Any]]:
        """semantic / episodic / style / relationship / appraisal / persona_patch の各パスを順に実行。"""
        return {
            "semantic": self.run_pass(
                "semantic",
                source_record_ids=source_record_ids,
                account_id=account_id,
                room_id=room_id,
            ),
            "episodic": self.run_pass(
                "episodic",
                source_record_ids=source_record_ids,
                account_id=account_id,
                room_id=room_id,
            ),
            "style": self.run_pass(
                "style",
                source_record_ids=source_record_ids,
                account_id=account_id,
                room_id=room_id,
            ),
            "relationship": self.run_pass(
                "relationship",
                source_record_ids=source_record_ids,
                account_id=account_id,
                room_id=room_id,
            ),
            "appraisal": self.run_pass(
                "appraisal",
                source_record_ids=source_record_ids,
                account_id=account_id,
                room_id=room_id,
            ),
            "persona_patch": self.run_pass(
                "persona_patch",
                source_record_ids=source_record_ids,
                account_id=account_id,
                room_id=room_id,
            ),
        }

    def _collect_records(
        self,
        source_record_ids: list[str] | None,
    ) -> tuple[list[str], list[Any]]:
        if source_record_ids is not None and source_record_ids:
            records: list[Any] = []
            for rid in source_record_ids:
                rec = self._archive.find_by_id(rid)
                if rec is not None:
                    records.append(rec)
            return source_record_ids, records
        records = self._archive.load_all()
        records = records[-self._batch_window() :]
        ids = [str(r.get("id", "")) for r in records]
        return ids, records

    def _batch_window(self) -> int:
        """``batch_max_chars`` を超えない範囲で最新のレコードを推定件数返す。

        1 レコード ≒ 200 文字と仮定して上限を求める。
        """
        avg = 200
        return max(1, self._config.batch_max_chars // avg)


__all__ = ["MemoryPipeline"]
