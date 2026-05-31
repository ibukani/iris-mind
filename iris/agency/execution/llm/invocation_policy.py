from __future__ import annotations

from iris.llm.capability import CapabilityChecker


class ModelInvocationPolicy:
    """LLM 呼び出し前の capability-based 判断を集約する。"""

    def __init__(self, capability_checker: CapabilityChecker | None = None) -> None:
        self._checker = capability_checker

    def resolve_tools(
        self,
        requested_tools: list[dict] | None,
        model_role: str,
    ) -> list[dict] | None:
        if not requested_tools:
            return None
        if self._checker and not self._checker.supports_tools(model_role):
            return None
        return requested_tools

    def resolve_thinking(self, requested: bool, model_role: str) -> bool:
        if not requested:
            return False
        return not (self._checker and not self._checker.supports_thinking(model_role))

    def resolve_temperature(
        self,
        explicit: float | None,
        level_temp: float | None,
        modulation_temp: float | None,
        config_temp: float,
    ) -> float:
        if explicit is not None:
            return explicit
        if level_temp is not None:
            return level_temp
        if modulation_temp is not None:
            return modulation_temp
        return config_temp
