"""
ContextManager — 会話履歴の compaction（要約）管理。

context_window を超えた会話履歴を自動要約し、コンテキスト制限を回避する。
"""

from __future__ import annotations

import json
from typing import Any

_COMPACT_PROMPT = """あなたはアシスタントIrisのコンテキスト管理システムです。
以下の会話履歴を要約してください。この要約は会話を継続するためのコンテキストとして使用されます。

以下の情報を必ず含めてください：
- これまでに達成したこと
- 現在進行中の作業
- 言及されたファイルやコード
- ユーザーからの重要なリクエストや制約
- 決定した技術的判断とその理由
- 次のステップ

簡潔だが、作業を継続できる十分な詳細を含めてください。日本語で記述すること。"""


def estimate_tokens(text: str) -> int:
    """テキストのトークン数を推定する（日本語は文字数/2、英語は文字数/4）。"""
    if not text:
        return 0
    return max(1, len(text) // 2)


def estimate_messages_tokens(messages: list[dict]) -> int:
    """メッセージリストの総トークン数を推定する。"""
    return sum(estimate_tokens(m.get("content", "")) for m in messages)


class ContextManager:
    """会話履歴の compaction を管理する。"""

    def __init__(self, llm: Any, compact_model: str | None = None) -> None:
        self.llm = llm
        self.compact_model = compact_model
        self._summary: str = ""

    def check_and_summarize(
        self,
        messages: list[dict],
        context_window: int,
        threshold: float = 0.85,
        preserve_last: int = 6,
    ) -> str:
        """
        トークン数が閾値を超えたら要約を実行する。

        Returns:
            要約文（変更がない場合は前回の要約を返す）
        """
        if context_window <= 0:
            return self._summary
        if len(messages) <= preserve_last:
            return self._summary

        total = estimate_messages_tokens(messages)
        if total <= context_window * threshold:
            return self._summary

        to_summarize = messages[:-preserve_last]
        summary = self._generate_summary(to_summarize)
        if summary:
            self._summary = summary
        return self._summary

    def force_summarize(
        self,
        messages: list[dict],
        instructions: str = "",
        preserve_last: int = 6,
    ) -> str:
        """強制的に要約を実行する。"""
        if len(messages) <= preserve_last:
            return self._summary
        to_summarize = messages[:-preserve_last]
        summary = self._generate_summary(to_summarize, instructions=instructions)
        if summary:
            self._summary = summary
        return self._summary

    @property
    def has_summary(self) -> bool:
        return bool(self._summary)

    @property
    def summary_text(self) -> str:
        return self._summary

    def clear(self) -> None:
        self._summary = ""

    def build_compact_messages(
        self,
        messages: list[dict],
        preserve_last: int = 6,
    ) -> list[dict]:
        """要約が存在する場合、古いメッセージを要約で置き換えたリストを返す。"""
        if not self._summary or len(messages) <= preserve_last:
            return messages
        summary_msg: dict = {
            "role": "system",
            "content": f"## Session Summary\n{self._summary}",
        }
        return [summary_msg] + messages[-preserve_last:]

    def _generate_summary(
        self,
        messages: list[dict],
        instructions: str = "",
    ) -> str:
        """LLM を呼び出して要約を生成する。"""
        prompt = _COMPACT_PROMPT
        if instructions:
            prompt += f"\n\n追加指示: {instructions}"
        truncated = [{"role": m["role"], "content": str(m.get("content", ""))[:500]} for m in messages]
        prompt += "\n\n" + json.dumps(truncated, ensure_ascii=False)

        resp = self.llm.chat(
            messages=[{"role": "user", "content": prompt}],
            model=self.compact_model,
            temperature=0.3,
            max_tokens=500,
            keep_alive="0",
        )
        return resp["message"].get("content", "").strip()
