from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Pathway(StrEnum):
    DIRECT = "direct"
    INDIRECT = "indirect"
    HYPERDIRECT = "hyperdirect"


@dataclass
class GateDecision:
    allow: bool
    pathway: Pathway
    reason: str | None = None
