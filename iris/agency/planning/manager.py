from __future__ import annotations

import logging

from iris.agency.bus import InternalBus, PlanDecided

logger = logging.getLogger(__name__)


class PlanningManager:
    def __init__(self, internal_bus: InternalBus) -> None:
        self._bus = internal_bus
        self._bus.subscribe("ExecutionResult", self._on_result)

    def handle(self, content: str, session_id: str = "", context: dict | None = None) -> None:
        plan = self._decide(content, context or {})
        plan["session_id"] = session_id
        self._bus.publish(PlanDecided(plan=plan))

    def _decide(self, content: str, context: dict) -> dict:
        return {"action": "respond", "content": content}

    def _on_result(self, event: object) -> None:
        pass
