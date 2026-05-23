from __future__ import annotations

from pathlib import Path
import time
from typing import Any

from loguru import logger
import orjson

from iris.limbic.models import DriveState, EmotionState


class PsychometricState:
    """全心理測定状態のメモリ一元管理 + 定期/シャットダウン永続化。

    === 集約対象（全データ型）===
      - EmotionState (PAD)     → self.emotion
      - DriveState             → self.drive
      - Big Five スコア       → self.big_five / self.big_five_history
      - PersonaData (話し方)   → self.speech_quirks
      - PersonaData (性格傾向) → self.state_traits
      - PersonaData (興味)     → self.interests

    === 永続化戦略 ===
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

        # --- 感情・欲求（PAD / Drive） ---
        self.emotion = EmotionState()
        self.drive = DriveState()

        # --- Big Five（OCEAN） ---
        self.big_five: dict[str, float] = {
            "openness": 50.0,
            "conscientiousness": 50.0,
            "extraversion": 50.0,
            "agreeableness": 50.0,
            "neuroticism": 50.0,
        }
        self.big_five_history: list[dict[str, Any]] = []

        # --- PersonaData（話し方・性格傾向・興味） ---
        self.speech_quirks: list[dict[str, Any]] = []
        self.state_traits: list[dict[str, Any]] = []
        self.interests: list[dict[str, Any]] = []

        self._load()

    # ================================================================
    # 永続化制御
    # ================================================================

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
            "emotion": self.emotion.to_dict(),
            "drive": self.drive.to_dict(),
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

    def _load(self) -> None:
        if not self._path.exists():
            logger.info("PsychometricState: starting fresh at {}", self._path)
            return
        try:
            raw = orjson.loads(self._path.read_bytes())
            if "emotion" in raw:
                self.emotion = EmotionState(**{k: float(v) for k, v in raw["emotion"].items() if k != "updated_at"})
            if "drive" in raw:
                self.drive = DriveState(
                    curiosity=raw["drive"].get("curiosity", 0.0),
                    social_need=raw["drive"].get("social_need", 0.0),
                    maintenance=raw["drive"].get("maintenance", 0.0),
                )
            if "big_five" in raw:
                self.big_five.update(raw["big_five"])
            self.big_five_history = raw.get("big_five_history", [])
            self.speech_quirks = raw.get("speech_quirks", [])
            self.state_traits = raw.get("state_traits", [])
            self.interests = raw.get("interests", [])
            logger.info("PsychometricState: loaded from {}", self._path)
        except (orjson.JSONDecodeError, Exception):
            logger.warning("PsychometricState: failed to load {}, starting fresh", self._path)

    # ================================================================
    # 簡易アクセサ
    # ================================================================

    @property
    def persona_data(self) -> dict[str, list[dict[str, Any]]]:
        """PersonaData 互換の辞書ビュー（後方互換）"""
        return {
            "speech_quirks": self.speech_quirks,
            "state_traits": self.state_traits,
            "interests": self.interests,
        }
