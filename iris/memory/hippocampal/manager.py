from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from iris.memory.hippocampal.reflexion import Reflexion
from iris.memory.manager import MemoryManager
from iris.memory.personality.persona_profile import PersonaProfile

if TYPE_CHECKING:
    from iris.memory.personality.big_five import BigFiveProfile

logger = logging.getLogger(__name__)


class HippocampalManager:
    def __init__(
        self,
        reflexion: Reflexion | None = None,
        memory: MemoryManager | None = None,
        persona_profile: PersonaProfile | None = None,
        big_five: BigFiveProfile | None = None,
        reflect_interval: int = 3,
    ) -> None:
        self._reflexion = reflexion
        self._memory = memory
        self._persona_profile = persona_profile
        self._big_five = big_five
        self._reflect_interval = reflect_interval

    def maybe_run(self, messages: list[dict], msg_count_since_reflect: int) -> int:
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

            if self._big_five is not None:
                bf_raw = result.get("big_five_estimate")
                if bf_raw:
                    try:
                        estimate = json.loads(bf_raw)
                        if isinstance(estimate, dict):
                            changes = self._big_five.update_from_estimate(estimate)
                            if changes:
                                logger.info("Big Five updated: %s", changes)
                    except (json.JSONDecodeError, TypeError):
                        logger.debug("Could not parse big_five_estimate: %s", bf_raw)

            self._maybe_consolidate_short_term()

            logger.info(
                "Quick reflect stored: speech_style=%s traits=%s reaction=%s",
                bool(result.get("speech_style")),
                bool(result.get("expressed_traits")),
                bool(result.get("user_reaction")),
            )
        except Exception as e:
            logger.exception("Quick reflect failed: %s", e)

        return 0

    def _maybe_consolidate_short_term(self) -> None:
        if self._memory is None:
            return
        stm = self._memory.short_term
        if not stm.should_consolidate():
            return
        unconsolidated = stm.get_unconsolidated_turns()
        if not unconsolidated:
            return
        user_turns = [t for t in unconsolidated if t.get("role") == "user"]
        if user_turns:
            combined = " | ".join(t["content"][:100] for t in user_turns[-3:])
            self._memory.long_term.store_episodic(
                {"content": f"[conversation] {combined}", "kind": "conversation"},
            )
        topics = stm.current_topics
        for topic in topics:
            self._memory.long_term.store_semantic(
                {"content": topic, "type": "topic", "tags": ["short_term_topic"]},
            )
        stm.mark_consolidated()
        logger.info("Hippocampal: consolidated %d turns, %d topics", len(unconsolidated), len(topics))

    def run_session(self, messages: list[dict], memory: MemoryManager | None = None) -> None:
        if self._reflexion is None:
            return
        if len(messages) < 2:
            return

        mem = memory or self._memory
        try:
            result = self._reflexion.reflect(messages)
            if result.get("summary") and mem:
                mem.add_episodic(
                    content=f"[session summary] {result['summary']}",
                    kind="system",
                )
            if mem:
                for key, entry_type in [
                    ("lesson", "lesson"),
                    ("preference", "preference"),
                    ("improvement", "lesson"),
                ]:
                    val = result.get(key, "")
                    if val:
                        mem.add_semantic_by_type(
                            entry_type=entry_type,
                            content=val,
                        )
            logger.info("Session reflect completed")
        except Exception as e:
            logger.exception("Session reflect failed: %s", e)
