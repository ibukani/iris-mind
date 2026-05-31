from __future__ import annotations

import random
from typing import Any


class SeedableRandom:
    """注入可能な乱数源。planning/context 内の確率的動作に使う。

    シード指定で決定論的テストを可能にする。
    """

    def __init__(self, seed: int | None = None) -> None:
        self._rng = random.Random(seed)

    def random(self) -> float:
        return self._rng.random()

    def choice(self, seq: list[Any]) -> Any:
        return self._rng.choice(seq)

    @classmethod
    def default(cls) -> SeedableRandom:
        return cls()
