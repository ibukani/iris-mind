from __future__ import annotations

from cachetools import LRUCache, cached
from loguru import logger

from iris.kernel.config import ModelConfig


class CapabilityChecker:
    """モデルの性能に基づき、機能を出し分ける。

    設定された capabilities が明示的な場合はそれを尊重し、
    未設定の場合は performance_tier から推定する。
    結果は role ごとにキャッシュされる。
    """

    def __init__(self, config: ModelConfig) -> None:
        self._config = config

    @cached(cache=LRUCache(maxsize=32))
    def supports_tools(self, role: str = "default") -> bool:
        caps = self._config.get_model_capabilities(role)
        if caps:
            result = "tools" in caps
            logger.info("CapabilityChecker: tools={} for role={} (explicit)", result, role)
            return result
        tier = self._config.get_model_performance_tier(role)
        result = tier in ("balanced", "capable")
        logger.info("CapabilityChecker: tools={} for role={} (tier={})", result, role, tier)
        return result

    @cached(cache=LRUCache(maxsize=32))
    def supports_thinking(self, role: str = "default") -> bool:
        caps = self._config.get_model_capabilities(role)
        if caps:
            result = "thinking" in caps
            logger.info("CapabilityChecker: thinking={} for role={} (explicit)", result, role)
            return result
        tier = self._config.get_model_performance_tier(role)
        result = tier == "capable"
        logger.info("CapabilityChecker: thinking={} for role={} (tier={})", result, role, tier)
        return result

    def get_performance_tier(self, role: str = "default") -> str:
        return self._config.get_model_performance_tier(role)
