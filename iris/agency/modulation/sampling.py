from __future__ import annotations

from iris.agency.modulation.state import ModulationState


def sampling_temperature(mod: ModulationState) -> float:
    """local LLM向けに小さく揺らす。感情値を直接promptへ出さない。"""
    base = 0.45 + mod.chaos_level * 0.35
    arousal_shift = max(0.0, mod.arousal) * 0.08 - max(0.0, -mod.arousal) * 0.04
    valence_shift = -0.03 if mod.valence < -0.35 else 0.02 if mod.valence > 0.35 else 0.0
    return max(0.2, min(0.9, base + arousal_shift + valence_shift))


def min_p_threshold(mod: ModulationState) -> float:
    """0.0 → 0.1 (標準), 1.0 → 0.02 (ほぼ全トークン候補)"""
    return max(0.02, 0.1 - mod.chaos_level * 0.08)
