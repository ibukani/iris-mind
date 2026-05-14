from __future__ import annotations

import time

from ..event.event import ProactiveSpeechEvent, UserInputEvent
from ..event.event_bus import EventBusProtocol
from ..services.proactive import ProactiveEngine

_NEGATIVE_RESPONSES = frozenset(
    {
        "やめて",
        "静かに",
        "stop",
        "やめろ",
        "黙れ",
        "うるさい",
        "やめてください",
        "shut up",
    }
)


class ProactiveResponseTracker:
    def __init__(self, proactive: ProactiveEngine, event_bus: EventBusProtocol) -> None:
        self._proactive = proactive
        self._pending: float = 0.0
        event_bus.subscribe("ProactiveSpeechEvent", self._on_proactive)
        event_bus.subscribe("UserInputEvent", self._on_user_input)

    def _on_proactive(self, event: ProactiveSpeechEvent) -> None:  # noqa: ARG002
        self._pending = time.time()

    def _on_user_input(self, event: UserInputEvent) -> None:
        if not self._pending:
            return
        elapsed = time.time() - self._pending
        self._pending = 0.0
        if elapsed > 60.0:
            return
        if event.content.strip().lower() in _NEGATIVE_RESPONSES:
            self._proactive.set_cooldown(600.0)
        else:
            self._proactive.notify_positive_response()


__all__ = ["ProactiveResponseTracker"]
