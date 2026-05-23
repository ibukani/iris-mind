"""
llm — LLM 基盤層。

プロバイダ管理、コンテキストウィンドウ管理、トークナイザー、
プロンプト構築、Capability 判定など、LLM との通信基盤を提供する。
"""

from __future__ import annotations

from .bridge import LLMBridge
from .capability import CapabilityChecker
from .context import LLMContextWindowManager, estimate_messages_tokens, estimate_tokens
from .interrupt_token import InterruptToken
from .priority_lock import PriorityLock
from .prompt import Personality
from .providers import (
    GoogleProvider,
    OllamaProvider,
    OpenRouterProvider,
    get_provider_class,
)
from .tokenizer import TokenizerManager

__all__ = [
    "CapabilityChecker",
    "GoogleProvider",
    "InterruptToken",
    "LLMBridge",
    "LLMContextWindowManager",
    "OllamaProvider",
    "OpenRouterProvider",
    "Personality",
    "PriorityLock",
    "TokenizerManager",
    "estimate_messages_tokens",
    "estimate_tokens",
    "get_provider_class",
]
