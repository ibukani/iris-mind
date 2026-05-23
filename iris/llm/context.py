from __future__ import annotations

from typing import Any
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage

from loguru import logger

from .bridge import LLMBridge
from .tokenizer import TokenizerManager

_COMPACT_PROMPT = """これまでの会話要約（もしあれば）と、新規の会話履歴を統合し、最新の会話要約を更新・作成してください。
作業継続に必要な情報のみを網羅し、冗長な内容は省いてください。

必須項目:
- 達成したこと / 進行中タスク
- 言及されたファイル・コード
- 次のステップ

日本語で簡潔に。"""


def estimate_tokens(text: str, tokenizer_mgr: TokenizerManager | None = None) -> int:
    """テキストのトークン数を概算する。

    TokenizerManagerが提供されていればそれを使用し、無ければ日本語マルチバイト文字を考慮した近似式を使用する。
    """
    if not text:
        return 0
    if tokenizer_mgr is not None:
        return tokenizer_mgr.estimate_tokens(text)
    # 日本語等のマルチバイトを考慮し、安全側に倒す (1文字あたり約1.3トークン)
    return int(len(text) * 1.3)


def estimate_messages_tokens(messages: list[BaseMessage], tokenizer_mgr: TokenizerManager | None = None) -> int:
    """メッセージ履歴全体の合計トークン数を概算する。"""
    return sum(estimate_tokens(str(m.content), tokenizer_mgr) for m in messages)


class LLMContextWindowManager:
    """LLM の context window 制限を超えた会話履歴を自動圧縮するクラス。

    LLM にはトークン上限（context_window）が存在する。
    このクラスは会話履歴のトークン数を監視し、閾値を超えた場合に
    LLM 要約を用いて古い履歴を圧縮する。

    純粋な工学的必要性への対応であり、脳科学上の対応構造は持たない。
    LLM の直近で動作するユーティリティとして llm 層に配置している。
    """

    def __init__(
        self,
        llm: LLMBridge | None = None,
        compact_model: str | None = None,
        tokenizers: dict[str, TokenizerManager] | None = None,
        default_model_name: str | None = None,
    ) -> None:
        self._llm = llm
        self._compact_model = compact_model
        self._tokenizers = tokenizers or {}
        self._default_model_name = default_model_name
        self._summary: str = ""

    def _get_tokenizer(self, model_name: str | None = None) -> TokenizerManager | None:
        """指定されたモデルに対応するトークナイザーを取得する。"""
        if model_name and model_name in self._tokenizers:
            return self._tokenizers[model_name]
        if self._default_model_name and self._default_model_name in self._tokenizers:
            return self._tokenizers[self._default_model_name]
        return None

    @property
    def summary(self) -> str:
        """現在の会話の要約テキストを取得する。"""
        return self._summary

    def check_and_summarize(
        self,
        messages: list[BaseMessage],
        context_window: int,
        threshold: float = 0.85,
        preserve_last: int = 6,
        model_name: str | None = None,
    ) -> str:
        """会話履歴がコンテキストウィンドウ制限に接近した場合、LLM要約で圧縮する。

        古い履歴（preserve_last 以外）を LLM で要約し、summary プロパティに保存する。
        要約文は、その後の chat() 呼び出しで session summary として
        システムプロンプトに注入される。

        Args:
            messages: 会話履歴（role/content のリスト）。
            context_window: LLM の context_window 上限（トークン数）。
            threshold: 圧縮トリガー閾値（デフォルト 85% = context_window * 0.85）。
            preserve_last: 直近 N 件のメッセージは圧縮対象外（デフォルト 6）。
            model_name: トークナイザー選択用のモデル名（省略時はdefault）。

        Returns:
            現在の session summary（自動更新された要約文、または前回の要約）。
        """
        if context_window <= 0:
            return self._summary
        if len(messages) <= preserve_last:
            return self._summary

        tokenizer = self._get_tokenizer(model_name)
        total = estimate_messages_tokens(messages, tokenizer)
        if total < context_window * threshold:
            return self._summary

        return self._compact(messages, preserve_last)

    def _compact(self, messages: list[BaseMessage], preserve_last: int = 6) -> str:
        """指定メッセージを切り出し、古いメッセージを要約して圧縮を実行する。"""
        summary = self.summarize(messages[:-preserve_last])
        self._summary = summary
        logger.info(
            "Context compacted: summary_len=%d, kept=%d messages",
            len(summary),
            preserve_last,
        )
        return summary

    def summarize(self, messages: list[BaseMessage]) -> str:
        """指定されたメッセージリストをLLMを使って1つの要約テキストにまとめる。"""
        if self._llm is None or not messages:
            return self._summary

        previous_summary_from_msg = ""
        new_messages = []
        for m in messages:
            role = getattr(m, "type", "?")
            content = str(m.content)
            if role == "system" and content.startswith("## Session Summary"):
                previous_summary_from_msg = content.replace("## Session Summary\n", "", 1).strip()
            else:
                new_messages.append(m)

        prev_summary = previous_summary_from_msg or self._summary

        # 新規メッセージをフォーマット（長いメッセージは適宜切り詰め）
        formatted_turns = []
        for m in new_messages:
            role = getattr(m, "type", "?")
            content = str(m.content)
            if len(content) > 1000:
                content = content[:1000] + "... (省略)"
            formatted_turns.append(f"{role}: {content}")

        text = "\n".join(formatted_turns)

        user_prompt = ""
        if prev_summary:
            user_prompt += f"■ 以前の会話要約:\n{prev_summary}\n\n"
        user_prompt += f"■ 新規の会話履歴:\n{text}"

        try:
            import asyncio

            resp = asyncio.run(
                self._llm.chat(
                    messages=[
                        SystemMessage(content=_COMPACT_PROMPT),
                        HumanMessage(content=user_prompt),
                    ],
                    model=self._compact_model,
                    temperature=0.3,
                    max_tokens=500,
                    num_ctx=4096,
                )
            )
            content = getattr(resp, "content", "")
            return str(content).strip()
        except Exception as e:
            logger.exception("Summarization failed: %s", e)
            return self._summary

    def compact(self, messages: list[BaseMessage]) -> str:
        """会話履歴全体の圧縮を外部から強制実行する。"""
        return self._compact(messages)
