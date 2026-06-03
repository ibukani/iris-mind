from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ModulationState:
    """人格変調状態。数値軸は内部制御に留め、prompt には自然語だけを渡す。

    このクラスは純粋なデータ保持のみを行い、振る舞いを一切含まない。
    計算/変換は siblings モジュール（sampling, prompt_guidance, behavior_policy）が行う。
    """

    chaos_level: float = 0.0
    valence: float = 0.0
    arousal: float = 0.0
    dominance: float = 0.0
    mood_label: str = "neutral"
    emotion_label: str = ""

    def __post_init__(self) -> None:
        self.chaos_level = max(0.0, min(1.0, self.chaos_level))
        self.valence = max(-1.0, min(1.0, self.valence))
        self.arousal = max(-1.0, min(1.0, self.arousal))
        self.dominance = max(-1.0, min(1.0, self.dominance))

    @classmethod
    def from_chaos_level(cls, level: float) -> ModulationState:
        return cls(chaos_level=level)
