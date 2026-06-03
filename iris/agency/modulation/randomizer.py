from __future__ import annotations

import random


class SeedableRandom:
    """注入可能な乱数源。デフォルトは random.Random（グローバル非依存）。

    シードを指定することで決定論的振る舞いをテスト可能にする。
    プロダクションではデフォルトコンストラクタ（非シード）で使用する。
    """

    def __init__(self, seed: int | None = None) -> None:
        self._rng = random.Random(seed)

    def random(self) -> float:
        return self._rng.random()

    @classmethod
    def default(cls) -> SeedableRandom:
        return cls()
