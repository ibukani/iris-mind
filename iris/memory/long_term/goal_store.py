from __future__ import annotations

from pathlib import Path

from loguru import logger
import orjson

from iris.memory.long_term.models import LongTermGoal


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
        logger.info("GoalStore: added goal '{}' (weight={:.2f})", description, weight)
        return goal.id

    def remove_goal(self, goal_id: str) -> bool:
        if goal_id in self._goals:
            logger.info("GoalStore: removed goal '{}'", self._goals[goal_id].description)
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

    def save(self, filepath: Path | str) -> None:
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = [g.model_dump() for g in self._goals.values()]
        with path.open("wb") as f:
            f.write(orjson.dumps(data, option=orjson.OPT_INDENT_2))
        logger.debug("GoalStore: saved {} goals to {}", len(data), path)

    def load(self, filepath: Path | str) -> None:
        path = Path(filepath)
        if not path.exists():
            return
        try:
            with path.open("rb") as f:
                data = orjson.loads(f.read())
            self._goals.clear()
            for item in data:
                goal = LongTermGoal.model_validate(item)
                self._goals[goal.id] = goal
            logger.info("GoalStore: loaded {} goals from {}", len(self._goals), path)
        except Exception as e:
            logger.error("GoalStore: failed to load goals from {}: {}", path, e)
