from __future__ import annotations

import time
import uuid

from pydantic import BaseModel, Field


class LongTermGoal(BaseModel):
    """エージェントの持続的な目標。"""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    description: str = ""
    weight: float = 1.0
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)

    def decay(self, amount: float) -> None:
        self.weight = max(0.0, self.weight - amount)
        self.updated_at = time.time()
