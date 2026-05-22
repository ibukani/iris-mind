from __future__ import annotations

from typing import Any, Protocol


class PlanStrategy(Protocol):
    def build(self, **kwargs: Any) -> dict[str, Any]: ...
