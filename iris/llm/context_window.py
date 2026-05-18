from __future__ import annotations

import logging

from iris.llm.provider import LLMProvider

logger = logging.getLogger(__name__)

_COMPACT_PROMPT = """会話履歴を要約してください。作業継続に必要な情報のみ含めてください。

必須項目:
- 達成したこと / 進行中タスク
- 言及されたファイル・コード
- 次のステップ

日本語で簡潔に。"""


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, len(text) // 2)


def estimate_messages_tokens(messages: list[dict]) -> int:
    return sum(estimate_tokens(m.get("content", "")) for m in messages)


class LLMContextWindowManager:
    """LLM の context window 制限を超えた会話履歴を自動圧縮する。

    LLM にはトークン上限（context_window）が存在する。
    このクラスは会話履歴のトークン数を監視し、閾値を超えた場合に
    LLM 要約を用いて古い履歴を圧縮する。

    純粋な工学的必要性への対応であり、脳科学上の対応構造は持たない。
    LLM の直近で動作するユーティリティとして llm 層に配置している。
    """

    def __init__(self, llm: LLMProvider | None = None, compact_model: str | None = None) -> None:
        self._llm = llm
        self._compact_model = compact_model
        self._summary: str = ""

    @property
    def summary(self) -> str:
        return self._summary

    def check_and_summarize(
        self,
        messages: list[dict],
        context_window: int,
        threshold: float = 0.85,
        preserve_last: int = 6,
    ) -> str:
        if context_window <= 0:
            return self._summary
        if len(messages) <= preserve_last:
            return self._summary

        total = estimate_messages_tokens(messages)
        if total < context_window * threshold:
            return self._summary

        return self._compact(messages, preserve_last)

    def _compact(self, messages: list[dict], preserve_last: int = 6) -> str:
        summary = self.summarize(messages[:-preserve_last])
        self._summary = summary
        logger.info(
            "Context compacted: summary_len=%d, kept=%d messages",
            len(summary),
            preserve_last,
        )
        return summary

    def summarize(self, messages: list[dict]) -> str:
        if self._llm is None or not messages:
            return self._summary

        text = "\n".join(f"{m.get('role', '?')}: {str(m.get('content', ''))[:300]}" for m in messages[-6:])
        try:
            resp = self._llm.chat(
                messages=[
                    {"role": "system", "content": _COMPACT_PROMPT},
                    {"role": "user", "content": f"会話履歴:\n{text}"},
                ],
                model=self._compact_model,
                temperature=0.3,
                max_tokens=300,
            )
            return resp.get("message", {}).get("content", "").strip()
        except Exception as e:
            logger.exception("Summarization failed: %s", e)
            return self._summary

    def compact(self, messages: list[dict]) -> str:
        return self._compact(messages)
