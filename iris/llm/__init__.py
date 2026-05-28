"""
llm — LLM 基盤層。

プロバイダ管理、コンテキストウィンドウ管理、トークナイザー、
プロンプト構築、Capability 判定など、LLM との通信基盤を提供する。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from iris.kernel.plugin import PluginCategory, PluginManifest, PluginPhase, PluginProtocol, discover_sub_plugins

from .bridge import LLMBridge
from .capability import CapabilityChecker
from .context import LLMContextWindowManager
from .interrupt_token import InterruptToken
from .priority_lock import PriorityLock
from .prompt import Personality
from .providers import (
    GoogleProvider,
    OllamaProvider,
    OpenRouterProvider,
    get_provider_class,
)
from .token_utils import estimate_messages_tokens, estimate_tokens
from .tokenizer import TokenizerManager

if TYPE_CHECKING:
    from iris.kernel.manager import PluginManager

MANIFEST = PluginManifest(
    name="llm",
    version="0.1.0",
    category=PluginCategory.CORE,
    phase=PluginPhase.CORE,
    dependencies=set(),
    provides=["LLMBridge", "TokenizerManager", "DebugCapture", "CapabilityChecker"],
    description="LLM基盤層",
)


class LlmPlugin:
    MANIFEST = MANIFEST

    def init(self, manager: PluginManager) -> None:
        manager.register_manifest(MANIFEST)
        config = manager.config

        llm = LLMBridge(model_config=config.model)

        tokenizers: dict[str, TokenizerManager] = {
            entry.name: TokenizerManager(
                repo_id=entry.tokenizer_repo_id,
                local_path=entry.tokenizer_local_path,
                hf_token=config.model.hf_token,
            )
            for entry in config.model.models
        }

        from iris.kernel.debug_capture import DebugCapture

        debug_capture = DebugCapture(
            tokenizer_mgr=next(iter(tokenizers.values()), None),
            auto_dump=config.debug.capture_auto_dump,
            max_entries=config.debug.capture_max_entries,
        )
        if config.debug.capture_enabled:
            debug_capture.set_enabled(True)

        capability_checker = CapabilityChecker(config=config.model)

        manager.provide(LLMBridge, llm)
        manager.provide(CapabilityChecker, capability_checker)

        from iris.kernel.debug_capture import DebugCapture

        manager.provide(DebugCapture, debug_capture)

        for sub_module in discover_sub_plugins("iris/llm/providers"):
            register_fn = getattr(sub_module, "register", None)
            if register_fn is not None:
                register_fn(llm)

        from .hooks import register_hooks

        register_hooks(manager)

    def start(self, manager: PluginManager) -> None:
        pass

    def stop(self, manager: PluginManager) -> None:
        pass


plugin: PluginProtocol = LlmPlugin()

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
