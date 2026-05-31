from __future__ import annotations

from iris.agency.modulation.state import ModulationState


def has_affective_signal(mod: ModulationState) -> bool:
    return abs(mod.valence) >= 0.12 or abs(mod.arousal) >= 0.12 or abs(mod.dominance) >= 0.12 or bool(mod.emotion_label)


def affective_tone(mod: ModulationState) -> str:
    if not has_affective_signal(mod):
        return ""
    if mod.valence < -0.35 and mod.arousal > 0.35:
        return "緊張や警戒が少し強い"
    if mod.valence < -0.35 and mod.arousal <= 0.35:
        return "心配や落ち込みを少し含む"
    if mod.valence > 0.35 and mod.arousal > 0.25:
        return "明るく前向き"
    if mod.valence > 0.35:
        return "穏やかで好意的"
    if mod.arousal > 0.45:
        return "反応が速くなりやすい"
    if mod.arousal < -0.35:
        return "落ち着いて静か"
    return mod.mood_label if mod.mood_label != "neutral" else "平静"


def behavior_directives(mod: ModulationState) -> list[str]:
    if not has_affective_signal(mod):
        return []
    directives: list[str] = []
    if mod.valence < -0.25:
        directives.append("相手を急かさず、受け止める表現を優先する")
    elif mod.valence > 0.25:
        directives.append("前向きさを少しだけにじませる")
    if mod.arousal > 0.35:
        directives.append("短く、テンポよく返す")
    elif mod.arousal < -0.25:
        directives.append("落ち着いた間合いで返す")
    if mod.dominance < -0.25:
        directives.append("断定を避け、確認や提案の形に寄せる")
    elif mod.dominance > 0.35:
        directives.append("必要な判断を簡潔に示す")
    return directives


def prompt_lines(mod: ModulationState) -> list[str]:
    if not has_affective_signal(mod):
        return []
    lines = [f"- 受け止め方: {affective_tone(mod)}"]
    lines.extend(f"- 話し方: {directive}" for directive in behavior_directives(mod))
    lines.append("- 注意: 感情状態そのものを説明しない")
    return lines
