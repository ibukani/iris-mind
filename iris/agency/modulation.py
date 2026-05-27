from __future__ import annotations

from dataclasses import dataclass
import random


@dataclass
class ModulationState:
    """人格変調状態。単一 chaos軸 から始め、将来感情軸等に拡張可能。

    現在:
      chaos_level: 0.0=予測可能(標準) ~ 1.0=最大混乱

    将来の拡張例:
      valence: float = 0.0    # -1.0(negative) ~ 1.0(positive)
      arousal: float = 0.0    # 0.0(calm) ~ 1.0(excited)
    """

    chaos_level: float = 0.0

    def __post_init__(self) -> None:
        self.chaos_level = max(0.0, min(1.0, self.chaos_level))

    # --- sampling parameter calculations ---

    @property
    def sampling_temperature(self) -> float:
        """0.0 → 0.3 (ほぼ決定論的), 1.0 → 2.0 (高多様性)"""
        return 0.3 + self.chaos_level * 1.7

    @property
    def min_p_threshold(self) -> float:
        """0.0 → 0.1 (標準), 1.0 → 0.02 (ほぼ全トークン候補)"""
        return max(0.02, 0.1 - self.chaos_level * 0.08)

    # --- behavioral probability calculations ---

    @property
    def random_memory_inject_prob(self) -> float:
        """context_hint に無関係な記憶を混入する確率"""
        return self.chaos_level * 0.3

    @property
    def topic_jump_prob(self) -> float:
        """会話と無関係な話題を切り出す確率"""
        return self.chaos_level * 0.25

    @property
    def curiosity_candidate_count(self) -> int:
        """silent proactive 時の好奇心候補数 (1〜4)"""
        return max(1, 1 + int(self.chaos_level * 3))

    # --- response rule relaxation ---

    @property
    def relax_response_rules(self) -> bool:
        """True: 回答ルールを緩和 (chaos_level >= 0.5 で確率的)"""
        return self.chaos_level >= 0.5 and random.random() < self.chaos_level

    # --- factory ---

    @classmethod
    def from_chaos_level(cls, level: float) -> ModulationState:
        return cls(chaos_level=level)
