from __future__ import annotations

from pathlib import Path
import time
from typing import Any

from loguru import logger
import orjson


class PsychometricState:
    """全心理測定状態のメモリ一元管理 + 定期/シャットダウン永続化。

    集約対象:
      - Big Five スコア + 進化履歴
      - PersonaData (speech_quirks, state_traits, interests)

    永続化戦略:
      - メモリ更新は即座 (mark_dirty)
      - ファイル書込は FLUSH_MAX_WRITES 回の蓄積または FLUSH_INTERVAL 秒経過で発火
      - シャットダウン時は flush() を明示呼び出し
    """

    FLUSH_INTERVAL = 30.0
    FLUSH_MAX_WRITES = 5

    def __init__(self, path: str = ".iris/data/psychometric_state.json") -> None:
        self._path = Path(path)
        self._dirty = False
        self._write_count = 0
        self._last_flush_time = 0.0

        self.big_five: dict[str, float] = {
            "openness": 50.0,
            "conscientiousness": 50.0,
            "extraversion": 50.0,
            "agreeableness": 50.0,
            "neuroticism": 50.0,
        }
        self.big_five_history: list[dict[str, Any]] = []

        self.speech_quirks: list[dict[str, Any]] = []
        self.state_traits: list[dict[str, Any]] = []
        self.interests: list[dict[str, Any]] = []

        self._load()

    # === public API ===

    def mark_dirty(self) -> None:
        self._dirty = True
        self._write_count += 1
        now = time.time()
        if self._write_count >= self.FLUSH_MAX_WRITES or now - self._last_flush_time >= self.FLUSH_INTERVAL:
            self.flush()

    def flush(self) -> None:
        if not self._dirty:
            return
        data: dict[str, Any] = {
            "big_five": {k: round(v, 1) for k, v in self.big_five.items()},
            "big_five_history": self.big_five_history[-50:],
            "speech_quirks": self.speech_quirks,
            "state_traits": self.state_traits,
            "interests": self.interests,
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_bytes(orjson.dumps(data, option=orjson.OPT_INDENT_2))
        self._dirty = False
        self._write_count = 0
        self._last_flush_time = time.time()
        logger.debug("PsychometricState: flushed to {}", self._path)

    # === 内部: 読込 ===

    def _load(self) -> None:
        if not self._path.exists():
            logger.info("PsychometricState: starting fresh at {}", self._path)
            return
        try:
            raw = orjson.loads(self._path.read_bytes())
            if "big_five" in raw:
                self.big_five.update(raw["big_five"])
            self.big_five_history = raw.get("big_five_history", [])
            self.speech_quirks = raw.get("speech_quirks", [])
            self.state_traits = raw.get("state_traits", [])
            self.interests = raw.get("interests", [])
            logger.info("PsychometricState: loaded from {}", self._path)
        except (orjson.JSONDecodeError, Exception):
            logger.warning("PsychometricState: failed to load {}, starting fresh", self._path)
