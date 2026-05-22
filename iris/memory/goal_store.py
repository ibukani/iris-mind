from __future__ import annotations

from dataclasses import dataclass, field
import logging
import time
import uuid

logger = logging.getLogger(__name__)


@dataclass
class LongTermGoal:
    """エージェントの持続的な目標（LongTermGoal）。

    Agency層が意思決定や思考を行う際の指針となる。
    重要度（weight）を持ち、時間経過やReflexion処理で減衰・忘却される。
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    description: str = ""
    weight: float = 1.0  # 0.0 ~ 1.0
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def decay(self, amount: float) -> None:
        self.weight = max(0.0, self.weight - amount)
        self.updated_at = time.time()


class GoalStore:
    """LongTermGoal を管理するストア。

    将来的にはファイルやDBに永続化するが、現在はインメモリ管理を基本とし、
    外部（MemoryManager）から定期的にダンプ・ロードされる想定。
    """

    def __init__(self) -> None:
        self._goals: dict[str, LongTermGoal] = {}

    def add_goal(self, description: str, weight: float = 1.0) -> str:
        goal = LongTermGoal(description=description, weight=max(0.0, min(1.0, weight)))
        self._goals[goal.id] = goal
        logger.info("GoalStore: added goal '%s' (weight=%.2f)", description, weight)
        return goal.id

    def remove_goal(self, goal_id: str) -> bool:
        if goal_id in self._goals:
            logger.info("GoalStore: removed goal '%s'", self._goals[goal_id].description)
            del self._goals[goal_id]
            return True
        return False

    def get_goals(self) -> list[LongTermGoal]:
        # 重要度（weight）順にソートして返す
        return sorted(self._goals.values(), key=lambda g: g.weight, reverse=True)

    def get_active_goals(self, threshold: float = 0.3) -> list[LongTermGoal]:
        return [g for g in self.get_goals() if g.weight >= threshold]

    def decay_goals(self, decay_rate: float, remove_threshold: float = 0.1) -> None:
        """目標の重要度を一律で減衰させ、閾値未満のものは忘却（削除）する。

        Reflexionやアイドル時のバッチ処理で呼ばれる。
        """
        to_remove = []
        for goal in self._goals.values():
            goal.decay(decay_rate)
            if goal.weight < remove_threshold:
                to_remove.append(goal.id)

        for gid in to_remove:
            self.remove_goal(gid)

    def clear(self) -> None:
        self._goals.clear()
        logger.info("GoalStore: cleared all goals")
