"""Token Estimation Utilities — トークン数推定のユーティリティ関数。

LLMContextWindowManager などから使用されるトークン推定関数を提供する。
"""

from __future__ import annotations

from langchain_core.messages import BaseMessage

from .tokenizer import TokenizerManager


def estimate_tokens(text: str, tokenizer_mgr: TokenizerManager | None = None) -> int:
    """テキストのトークン数を概算する。

    TokenizerManagerが提供されていればそれを使用し、無ければ日本語マルチバイト文字を考慮した近似式を使用する。
    """
    if not text:
        return 0
    if tokenizer_mgr is not None:
        return int(tokenizer_mgr.estimate_tokens(text))
    # 日本語等のマルチバイトを考慮し、安全側に倒す (1文字あたり約1.3トークン)
    return int(len(text) * 1.3)


def estimate_messages_tokens(messages: list[BaseMessage], tokenizer_mgr: TokenizerManager | None = None) -> int:
    """メッセージ履歴全体の合計トークン数を概算する。"""
    return sum(estimate_tokens(str(m.content), tokenizer_mgr) for m in messages)
