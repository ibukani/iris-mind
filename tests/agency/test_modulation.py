from __future__ import annotations

from iris.agency.execution.llm.prompt_builder import SystemPromptBuilder
from iris.agency.modulation import ModulationState, check_relax_response_rules, sampling_temperature
from iris.agency.modulation import prompt_lines as _prompt_lines
from iris.agency.modulation.prompt_guidance import has_affective_signal
from iris.agency.modulation.randomizer import SeedableRandom
from iris.llm.prompt import Personality


def test_modulation_clamps_vad_axes() -> None:
    mod = ModulationState(chaos_level=2.0, valence=9.0, arousal=-9.0, dominance=3.0)

    assert mod.chaos_level == 1.0
    assert mod.valence == 1.0
    assert mod.arousal == -1.0
    assert mod.dominance == 1.0


def test_modulation_prompt_lines_use_natural_language() -> None:
    mod = ModulationState(valence=-0.6, arousal=0.5, dominance=-0.4, mood_label="警戒")

    text = "\n".join(_prompt_lines(mod))

    assert "緊張" in text
    assert "急かさず" in text
    assert "感情状態そのものを説明しない" in text
    assert not any(ch.isdigit() for ch in text)


def test_modulation_sampling_temperature_stays_local_llm_range() -> None:
    cold = ModulationState(chaos_level=0.0, arousal=-1.0)
    hot = ModulationState(chaos_level=1.0, arousal=1.0)

    assert 0.2 <= sampling_temperature(cold) <= 0.9
    assert 0.2 <= sampling_temperature(hot) <= 0.9
    assert sampling_temperature(cold) < sampling_temperature(hot)


def test_personality_adds_affective_guidance_section() -> None:
    personality = Personality()
    mod = ModulationState(valence=0.6, arousal=0.4)

    prompt = personality.build_system_prompt(affective_guidance="\n".join(_prompt_lines(mod)))

    assert "## Irisの現在の応答傾向" in prompt
    assert "前向き" in prompt
    assert "VAD" not in prompt
    assert "valence" not in prompt


def test_system_prompt_builder_wires_modulation() -> None:
    builder = SystemPromptBuilder(personality=Personality())
    mod = ModulationState(valence=-0.5, arousal=0.6, dominance=-0.5)

    messages = builder.build(modulation=mod)
    profile = str(messages[0].content)

    assert "## Irisの現在の応答傾向" in profile
    assert "急かさず" in profile
    assert "VAD" not in profile
    assert "valence" not in profile


def test_relax_response_rules_deterministic_with_seed() -> None:
    mod = ModulationState(chaos_level=0.8)
    rng = SeedableRandom(seed=42)

    results = [check_relax_response_rules(mod, rng=rng) for _ in range(5)]
    expected = [check_relax_response_rules(mod, rng=SeedableRandom(seed=42)) for _ in range(5)]

    assert results == expected


def test_relax_response_rules_low_chaos_never_relaxes() -> None:
    mod = ModulationState(chaos_level=0.3)
    assert not check_relax_response_rules(mod)
    assert not check_relax_response_rules(mod)


def test_has_affective_signal() -> None:
    neutral = ModulationState()
    assert not has_affective_signal(neutral)

    emotional = ModulationState(valence=0.3)
    assert has_affective_signal(emotional)
