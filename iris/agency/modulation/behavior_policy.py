from __future__ import annotations

from iris.agency.modulation.randomizer import SeedableRandom
from iris.agency.modulation.state import ModulationState


def should_suppress_proactive(mod: ModulationState) -> bool:
    return mod.valence < -0.45 and mod.arousal > 0.35


def _default_rng() -> SeedableRandom:
    return SeedableRandom.default()


def check_relax_response_rules(
    mod: ModulationState,
    rng: SeedableRandom | None = None,
) -> bool:
    """True: 回答ルールを緩和 (chaos_level >= 0.5 で確率的)。

    同じ ModulationState でも呼び出しごとに異なる値を返す可能性がある。
    テストではシード指定した SeedableRandom を注入して決定論的にできる。
    """
    if mod.chaos_level < 0.5:
        return False
    rng = rng or _default_rng()
    return rng.random() < mod.chaos_level


def random_memory_inject_prob(mod: ModulationState) -> float:
    """context_hint に無関係な記憶を混入する確率。純粋に確率値のみ。"""
    return mod.chaos_level * 0.3


def topic_jump_prob(mod: ModulationState) -> float:
    """会話と無関係な話題を切り出す確率。純粋に確率値のみ。"""
    return mod.chaos_level * 0.25


def curiosity_candidate_count(mod: ModulationState) -> int:
    """silent proactive 時の好奇心候補数 (1〜4)。純粋に整数値のみ。"""
    return max(1, 1 + int(mod.chaos_level * 3))
