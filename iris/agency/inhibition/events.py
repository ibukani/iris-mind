from __future__ import annotations

from enum import StrEnum

from iris.event.base import Event


class InhibitionAction(StrEnum):
    SUPPRESS = "suppress"
    UNSUPPRESS = "unsuppress"
    HYPERDIRECT = "hyperdirect"


class InhibitionEvent(Event):
    action: InhibitionAction = InhibitionAction.SUPPRESS
    reason: str = ""
    duration: float = 0.0
    room_id: str = ""
