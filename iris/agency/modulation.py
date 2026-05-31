from __future__ import annotations

from dataclasses import dataclass
import random


@dataclass
class ModulationState:
    """人格変調状態。数値軸は内部制御に留め、prompt には自然語だけを渡す。"""

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

    # --- sampling parameter calculations ---

    @property
    def sampling_temperature(self) -> float:
        """local LLM向けに小さく揺らす。感情値を直接promptへ出さない。"""
        base = 0.45 + self.chaos_level * 0.35
        arousal_shift = max(0.0, self.arousal) * 0.08 - max(0.0, -self.arousal) * 0.04
        valence_shift = -0.03 if self.valence < -0.35 else 0.02 if self.valence > 0.35 else 0.0
        return max(0.2, min(0.9, base + arousal_shift + valence_shift))

    @property
    def min_p_threshold(self) -> float:
        """0.0 → 0.1 (標準), 1.0 → 0.02 (ほぼ全トークン候補)"""
        return max(0.02, 0.1 - self.chaos_level * 0.08)

    # --- affective language for prompts ---

    @property
    def has_affective_signal(self) -> bool:
        return (
            abs(self.valence) >= 0.12
            or abs(self.arousal) >= 0.12
            or abs(self.dominance) >= 0.12
            or bool(self.emotion_label)
        )

    @property
    def affective_tone(self) -> str:
        if not self.has_affective_signal:
            return ""
        if self.valence < -0.35 and self.arousal > 0.35:
            return "緊張や警戒が少し強い"
        if self.valence < -0.35 and self.arousal <= 0.35:
            return "心配や落ち込みを少し含む"
        if self.valence > 0.35 and self.arousal > 0.25:
            return "明るく前向き"
        if self.valence > 0.35:
            return "穏やかで好意的"
        if self.arousal > 0.45:
            return "反応が速くなりやすい"
        if self.arousal < -0.35:
            return "落ち着いて静か"
        return self.mood_label if self.mood_label != "neutral" else "平静"

    @property
    def behavior_directives(self) -> list[str]:
        if not self.has_affective_signal:
            return []
        directives: list[str] = []
        if self.valence < -0.25:
            directives.append("相手を急かさず、受け止める表現を優先する")
        elif self.valence > 0.25:
            directives.append("前向きさを少しだけにじませる")
        if self.arousal > 0.35:
            directives.append("短く、テンポよく返す")
        elif self.arousal < -0.25:
            directives.append("落ち着いた間合いで返す")
        if self.dominance < -0.25:
            directives.append("断定を避け、確認や提案の形に寄せる")
        elif self.dominance > 0.35:
            directives.append("必要な判断を簡潔に示す")
        return directives

    @property
    def prompt_lines(self) -> list[str]:
        if not self.has_affective_signal:
            return []
        lines = [f"- 受け止め方: {self.affective_tone}"]
        lines.extend(f"- 話し方: {directive}" for directive in self.behavior_directives)
        lines.append("- 注意: 感情状態そのものを説明しない")
        return lines

    @property
    def should_suppress_proactive(self) -> bool:
        return self.valence < -0.45 and self.arousal > 0.35

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
