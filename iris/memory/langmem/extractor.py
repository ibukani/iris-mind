"""LangMem Extractor — ローカル ChatModel から候補を抽出する。

責務:
- ``LLMBridge.get_chat_model_for_role("memory")`` でローカル ChatModel を取得
- ``langmem.create_thread_extractor`` で小さなパスごとの Runnable を作成
- 抽出結果は ``MemoryCandidate`` として ``MemoryCandidateStore`` に書き込む
- 失敗しても例外を呼び出し側に伝播させず、ジョブを ``failed`` にマークする
"""

from __future__ import annotations

from collections.abc import Callable
import json
from typing import Any

from loguru import logger

from iris.memory.archive.models import ConversationRecord
from iris.memory.langmem.dedup import compute_candidate_hash
from iris.memory.langmem.models import (
    MemoryCandidate,
    MemoryExtractionJob,
    PassType,
    TargetStore,
)
from iris.memory.langmem.prompts import (
    APPRAISAL_INSTRUCTIONS,
    EPISODIC_INSTRUCTIONS,
    PERSONA_PATCH_INSTRUCTIONS,
    RELATIONSHIP_INSTRUCTIONS,
    SEMANTIC_INSTRUCTIONS,
    STYLE_INSTRUCTIONS,
)
from iris.memory.langmem.schemas import (
    AppraisalExtractionResult,
    EpisodicExtractionResult,
    PersonaPatchExtractionResult,
    RelationshipExtractionResult,
    SemanticExtractionResult,
    StyleExtractionResult,
)
from iris.memory.langmem.stores import MemoryCandidateStore

_INSTRUCTIONS_BY_PASS: dict[PassType, str] = {
    "semantic": SEMANTIC_INSTRUCTIONS,
    "episodic": EPISODIC_INSTRUCTIONS,
    "style": STYLE_INSTRUCTIONS,
    "relationship": RELATIONSHIP_INSTRUCTIONS,
    "appraisal": APPRAISAL_INSTRUCTIONS,
    "persona_patch": PERSONA_PATCH_INSTRUCTIONS,
}

_SCHEMAS_BY_PASS: dict[PassType, type] = {
    "semantic": SemanticExtractionResult,
    "episodic": EpisodicExtractionResult,
    "style": StyleExtractionResult,
    "relationship": RelationshipExtractionResult,
    "appraisal": AppraisalExtractionResult,
    "persona_patch": PersonaPatchExtractionResult,
}


class LangMemExtractor:
    """ローカル LLM を用いた LangMem ベース候補抽出器。"""

    def __init__(
        self,
        *,
        chat_model: Any,
        candidate_store: MemoryCandidateStore,
        instructions_by_pass: dict[PassType, str] | None = None,
        schemas_by_pass: dict[PassType, type] | None = None,
        thread_extractor_factory: Callable[[Any, type, str], Any] | None = None,
        scope_resolver: Callable[[PassType, dict[str, Any]], tuple[str, str]] | None = None,
    ) -> None:
        self._chat_model = chat_model
        self._candidate_store = candidate_store
        self._instructions = instructions_by_pass or dict(_INSTRUCTIONS_BY_PASS)
        self._schemas = schemas_by_pass or dict(_SCHEMAS_BY_PASS)
        self._thread_extractor_factory = thread_extractor_factory or _default_thread_extractor_factory
        self._scope_resolver = scope_resolver or _default_scope_resolver
        self._extractors: dict[PassType, Any] = {}
        self._init_extractors()

    def _init_extractors(self) -> None:
        for pass_type, schema in self._schemas.items():
            try:
                self._extractors[pass_type] = self._thread_extractor_factory(
                    self._chat_model, schema, self._instructions[pass_type]
                )
            except Exception as e:  # pragma: no cover - depends on langmem internals
                logger.warning("LangMemExtractor: init failed for pass={} err={}", pass_type, e)

    def run(
        self,
        job: MemoryExtractionJob,
        records: list[ConversationRecord | dict[str, Any]],
        *,
        scope_resolver: Callable[[PassType, dict[str, Any]], tuple[str, str]] | None = None,
    ) -> list[MemoryCandidate]:
        """``job`` に対応する抽出パスを実行し、生成された候補をストアに書き出す。

        ``scope_resolver`` を渡すと ``Job.account_id/room_id`` 以外の文脈で
        候補ごとのスコープを決定できる。省略時は ``self._scope_resolver``、
        それも空文字を返す場合は ``Job.account_id/room_id`` にフォールバック。
        """
        if job.pass_type not in self._extractors:
            logger.warning("LangMemExtractor: no extractor available for pass={}", job.pass_type)
            return []
        messages = _records_to_messages(records)
        if not messages:
            return []
        try:
            result = self._extractors[job.pass_type].invoke({"messages": messages})
        except Exception as e:
            logger.warning("LangMemExtractor: invoke failed pass={} err={}", job.pass_type, e)
            return []
        items = _extract_items(result)
        if not items:
            return []
        resolver = scope_resolver or self._scope_resolver
        candidates: list[MemoryCandidate] = []
        target_store: TargetStore = _target_store_for_pass(job.pass_type)  # type: ignore[assignment]
        for it in items:
            payload = it if isinstance(it, dict) else it.model_dump(mode="python")
            confidence = float(payload.get("confidence", 0.0) or 0.0)
            account_id, room_id = resolver(job.pass_type, payload)
            if not account_id:
                account_id = job.account_id
            if not room_id:
                room_id = job.room_id
            payload_hash = compute_candidate_hash(
                target_store=target_store,
                payload=payload,
                account_id=account_id,
                room_id=room_id,
            )
            candidate = MemoryCandidate(
                source_record_ids=list(job.source_record_ids),
                job_id=job.id,
                target_store=target_store,
                payload=payload,
                confidence=confidence,
                payload_hash=payload_hash,
                scope_account_id=account_id,
                scope_room_id=room_id,
            )
            self._candidate_store.add(candidate)
            candidates.append(candidate)
        return candidates

    @property
    def available_passes(self) -> list[PassType]:
        return list(self._extractors.keys())


def _default_thread_extractor_factory(model: Any, schema: type, instructions: str) -> Any:
    """``langmem.create_thread_extractor`` への薄いラッパー。テストで差し替え可能。"""
    from langmem import create_thread_extractor  # type: ignore[import-untyped]

    return create_thread_extractor(model, schema=schema, instructions=instructions)


def _default_scope_resolver(
    pass_type: PassType,
    payload: dict[str, Any],
) -> tuple[str, str]:
    """候補から ``(account_id, room_id)`` を抽出する。

    LangMem 出力は通常 ``scope`` ('account'|'room'|'global') のみ持つので、
    アカウント ID / ルーム ID を特定するには ``Job.metadata`` などの追加情報が必要。
    デフォルトでは空文字を返し、``scope`` を ``scope_account_id/room_id`` には
    反映しない (本番では builder から明示的な resolver を注入する想定)。
    """
    del pass_type, payload
    return ("", "")


def make_job_scope_resolver(account_id: str, room_id: str) -> Callable[[PassType, dict[str, Any]], tuple[str, str]]:
    """``Job.account_id/room_id`` をそのまま返す resolver を生成する。"""

    def _resolve(_pass: PassType, _payload: dict[str, Any]) -> tuple[str, str]:
        return (account_id, room_id)

    return _resolve


def _records_to_messages(records: list[ConversationRecord | dict[str, Any]]) -> list[Any]:
    """ConversationRecord 群を LangChain messages へ変換する。"""
    from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

    msgs: list[Any] = []
    for r in records:
        if isinstance(r, ConversationRecord):
            content = r.content
            role: str = r.role
        else:
            content = str(r.get("content", ""))
            role_value = r.get("role", "user")
            role = role_value if isinstance(role_value, str) else "user"
        if not content:
            continue
        if role == "user":
            msgs.append(HumanMessage(content=content))
        elif role == "assistant":
            msgs.append(AIMessage(content=content))
        else:
            msgs.append(SystemMessage(content=content))
    return msgs


def _extract_items(result: Any) -> list[Any]:
    """extract 結果を ``list[item]`` 形に正規化する。"""
    if result is None:
        return []
    if hasattr(result, "items"):
        return list(result.items or [])
    if isinstance(result, dict):
        items = result.get("items")
        if isinstance(items, list):
            return items
    if isinstance(result, list):
        return result
    return []


def _target_store_for_pass(pass_type: PassType) -> str:
    mapping: dict[PassType, str] = {
        "semantic": "semantic",
        "episodic": "episodic",
        "style": "style",
        "relationship": "relationship",
        "appraisal": "appraisal",
        "persona_patch": "persona_patch",
    }
    return mapping[pass_type]


def safe_loads_json(raw: str) -> Any:
    """モデル出力が壊れている時に備えた JSON フォールバックパーサ。"""
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return None


__all__ = ["LangMemExtractor", "make_job_scope_resolver", "safe_loads_json"]
