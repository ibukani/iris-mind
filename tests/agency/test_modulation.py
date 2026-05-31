from __future__ import annotations

from iris.agency.execution.llm.prompt_builder import SystemPromptBuilder
from iris.agency.modulation import ModulationState
from iris.llm.prompt import Personality


def test_modulation_clamps_vad_axes() -> None:
    mod = ModulationState(chaos_level=2.0, valence=9.0, arousal=-9.0, dominance=3.0)

    assert mod.chaos_level == 1.0
    assert mod.valence == 1.0
    assert mod.arousal == -1.0
    assert mod.dominance == 1.0


def test_modulation_prompt_lines_use_natural_language() -> None:
    mod = ModulationState(valence=-0.6, arousal=0.5, dominance=-0.4, mood_label="警戒")

    text = "\n".join(mod.prompt_lines)

    assert "緊張" in text
    assert "急かさず" in text
    assert "感情状態そのものを説明しない" in text
    assert not any(ch.isdigit() for ch in text)


def test_modulation_sampling_temperature_stays_local_llm_range() -> None:
    cold = ModulationState(chaos_level=0.0, arousal=-1.0)
    hot = ModulationState(chaos_level=1.0, arousal=1.0)

    assert 0.2 <= cold.sampling_temperature <= 0.9
    assert 0.2 <= hot.sampling_temperature <= 0.9
    assert cold.sampling_temperature < hot.sampling_temperature


def test_personality_adds_affective_guidance_section() -> None:
    personality = Personality()
    mod = ModulationState(valence=0.6, arousal=0.4)

    prompt = personality.build_system_prompt(affective_guidance="\n".join(mod.prompt_lines))

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
