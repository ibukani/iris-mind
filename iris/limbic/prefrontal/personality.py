from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from loguru import logger
import orjson

_DEFAULT_PATH = ".iris/data/big_five.json"

_PEM_LAMBDA = 0.8

_CHANGE_THRESHOLD = 1.0


def _default_ocean() -> dict[str, float]:
    return {
        "openness": 50.0,
        "conscientiousness": 50.0,
        "extraversion": 50.0,
        "agreeableness": 50.0,
        "neuroticism": 50.0,
    }


_TRAIT_LABELS: dict[str, str] = {
    "openness": "開放性 (Openness)",
    "conscientiousness": "誠実性 (Conscientiousness)",
    "extraversion": "外向性 (Extraversion)",
    "agreeableness": "協調性 (Agreeableness)",
    "neuroticism": "神経症的傾向 (Neuroticism)",
}


@dataclass
class BigFiveProfile:
    """Big Five 性格特性モデル（OCEAN）。

    特性値は 0-100 の範囲で管理。
    会話からの推定値（p_turn）を指数移動平均（PEM）で更新する。
    """

    openness: float = 50.0
    conscientiousness: float = 50.0
    extraversion: float = 50.0
    agreeableness: float = 50.0
    neuroticism: float = 50.0
    evolution_history: list[dict[str, Any]] = field(default_factory=list)
    _path: str = _DEFAULT_PATH

    @classmethod
    def load(cls, path: str = _DEFAULT_PATH) -> BigFiveProfile:
        p = Path(path)
        if not p.exists():
            profile = cls(_path=path)
            profile._save()
            logger.info("BigFiveProfile: created new profile")
            return profile
        try:
            data = orjson.loads(p.read_bytes())
            logger.info("BigFiveProfile: loaded from %s", path)
            return cls(
                openness=data.get("openness", 50.0),
                conscientiousness=data.get("conscientiousness", 50.0),
                extraversion=data.get("extraversion", 50.0),
                agreeableness=data.get("agreeableness", 50.0),
                neuroticism=data.get("neuroticism", 50.0),
                evolution_history=data.get("evolution_history", []),
                _path=path,
            )
        except (orjson.JSONDecodeError, Exception):
            return cls(_path=path)

    def save(self) -> None:
        self._save()

    def _save(self) -> None:
        p = Path(self._path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(
            orjson.dumps(self.to_dict(), option=orjson.OPT_INDENT_2),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "openness": round(self.openness, 1),
            "conscientiousness": round(self.conscientiousness, 1),
            "extraversion": round(self.extraversion, 1),
            "agreeableness": round(self.agreeableness, 1),
            "neuroticism": round(self.neuroticism, 1),
            "evolution_history": self.evolution_history[-50:],
        }

    def get_state(self) -> dict:
        return {
            "scores": self.get_scores(),
            "recent_changes": self.evolution_history[-10:],
        }

    def get_scores(self) -> dict[str, float]:
        return {k: round(getattr(self, k), 1) for k in _default_ocean()}

    def format_summary(self) -> str:
        lines = [f"- {_TRAIT_LABELS[k]}: {v:.0f}" for k, v in self.get_scores().items()]
        return "## 性格特性 (Big Five)\n" + "\n".join(lines)

    def update_from_estimate(self, estimate: dict[str, float], source: str = "reflection") -> list[str]:
        changes: list[str] = []
        now = datetime.now(UTC).isoformat(timespec="seconds")

        for trait in _default_ocean():
            p_old = getattr(self, trait)
            p_turn = estimate.get(trait)
            if p_turn is None:
                continue
            p_new = _PEM_LAMBDA * p_old + (1 - _PEM_LAMBDA) * p_turn
            setattr(self, trait, round(max(0.0, min(100.0, p_new)), 1))

            delta = abs(p_new - p_old)
            if delta > _CHANGE_THRESHOLD:
                direction = "上昇" if p_new > p_old else "下降"
                msg = f"{_TRAIT_LABELS[trait]}: {p_old:.0f} → {p_new:.0f} ({direction}, delta={delta:.1f})"
                changes.append(msg)
                self.evolution_history.append(
                    {
                        "trait": trait,
                        "from": round(p_old, 1),
                        "to": round(p_new, 1),
                        "delta": round(delta, 1),
                        "source": source,
                        "timestamp": now,
                    }
                )

        if changes:
            self.evolution_history.append(
                {
                    "event": "personality_change",
                    "changes": changes,
                    "timestamp": now,
                }
            )
            for c in changes:
                logger.info("BigFiveProfile: %s", c)

        self._save()
        return changes
