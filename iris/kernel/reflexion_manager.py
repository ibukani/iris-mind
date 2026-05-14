from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class ReflexionManager:
    """Reflexion のスケジューリングと結果の永続化を担当。"""

    def __init__(
        self,
        reflexion: Any | None = None,
        memory: Any | None = None,
        persona_profile: Any | None = None,
        reflect_interval: int = 3,
    ) -> None:
        self._reflexion = reflexion
        self._memory = memory
        self._persona_profile = persona_profile
        self._reflect_interval = reflect_interval

    def maybe_run(self, messages: list[dict], msg_count_since_reflect: int) -> int:
        """Nターンごとに quick_reflect を実行する。更新されたカウンタを返す。"""
        if self._reflexion is None:
            return msg_count_since_reflect
        if msg_count_since_reflect < self._reflect_interval:
            return msg_count_since_reflect
        if len(messages) < 2:
            return msg_count_since_reflect

        try:
            result = self._reflexion.quick_reflect(messages)

            if result.get("speech_style") and self._memory:
                self._memory.add_semantic_by_type(
                    entry_type="trait",
                    content=f"Irisの話し方: {result['speech_style']}",
                    tags=["speech_style"],
                )
            if result.get("expressed_traits") and self._memory:
                self._memory.add_semantic_by_type(
                    entry_type="trait",
                    content=f"Irisの性格特性: {result['expressed_traits']}",
                    tags=["personality_trait"],
                )
            if result.get("user_reaction") and self._memory:
                self._memory.add_semantic_by_type(
                    entry_type="preference",
                    content=f"ユーザーの反応傾向: {result['user_reaction']}",
                    tags=["user_reaction"],
                )
            if self._persona_profile is not None:
                self._persona_profile.update_from_reflection(result)

            logger.info(
                "Quick reflect stored: speech_style=%s traits=%s reaction=%s",
                bool(result.get("speech_style")),
                bool(result.get("expressed_traits")),
                bool(result.get("user_reaction")),
            )
        except Exception as e:
            logger.exception("Quick reflect failed: %s", e)

        return 0

    def run_session(self, messages: list[dict]) -> None:
        """セッション終了時に full reflect を実行する。"""
        if self._reflexion is None:
            return
        if len(messages) < 2:
            return

        try:
            result = self._reflexion.reflect(messages)
            if result.get("summary") and self._memory:
                self._memory.add_episodic(
                    content=f"[session summary] {result['summary']}",
                    _kind="system",
                )
            if self._memory:
                for key, entry_type in [
                    ("lesson", "lesson"),
                    ("preference", "preference"),
                    ("improvement", "lesson"),
                ]:
                    val = result.get(key, "")
                    if val:
                        self._memory.add_semantic_by_type(
                            entry_type=entry_type,
                            content=val,
                        )
            logger.info("Session reflect completed")
        except Exception as e:
            logger.exception("Session reflect failed: %s", e)
