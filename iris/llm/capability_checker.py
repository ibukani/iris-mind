from __future__ import annotations

from iris.kernel.config import ModelConfig


class CapabilityChecker:
    """モデルの性能に基づき、機能を出し分ける。

    設定された capabilities が明示的な場合はそれを尊重し、
    未設定の場合は performance_tier から推定する。
    """

    def __init__(self, config: ModelConfig) -> None:
        self._config = config

    def supports_tools(self, role: str = "default") -> bool:
        caps = self._config.get_model_capabilities(role)
        if caps:
            return "tools" in caps
        tier = self._config.get_model_performance_tier(role)
        return tier in ("balanced", "capable")

    def supports_thinking(self, role: str = "default") -> bool:
        caps = self._config.get_model_capabilities(role)
        if caps:
            return "thinking" in caps
        tier = self._config.get_model_performance_tier(role)
        return tier == "capable"

    def get_performance_tier(self, role: str = "default") -> str:
        return self._config.get_model_performance_tier(role)
