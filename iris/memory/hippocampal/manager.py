from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from iris.memory.manager import MemoryManagerProtocol
    from iris.memory.personality.big_five import BigFiveProfile
    from iris.memory.personality.persona_profile import PersonaProfile

from iris.event.event_types import DebugSnapshotEvent
from iris.memory.hippocampal.reflexion import ReflexionProtocol

logger = logging.getLogger(__name__)


class HippocampalManagerProtocol(Protocol):
    """海馬マネージャーのインターフェース。

    なぜこの設計にしたか:
    短期記憶から長期記憶への定着（コンソリデーション）および省察処理をモック化または
    別のアプローチで差し替え可能にし、テスト容易性と柔軟性を向上させるため。
    """

    def maybe_run(self, messages: list[dict], msg_count_since_reflect: int) -> int: ...
    def force_run(self, messages: list[dict]) -> None: ...
    def run_session(self, messages: list[dict], memory: MemoryManagerProtocol | None = None) -> None: ...


class HippocampalManager:
    def __init__(
        self,
        reflexion: ReflexionProtocol | None = None,
        memory: MemoryManagerProtocol | None = None,
        persona_profile: PersonaProfile | None = None,
        big_five: BigFiveProfile | None = None,
        reflect_interval: int = 3,
        event_bus: Any = None,
    ) -> None:
        self._reflexion = reflexion
        self._memory = memory
        self._persona_profile = persona_profile
        self._big_five = big_five
        self._reflect_interval = reflect_interval
        self._event_bus = event_bus

    def maybe_run(self, messages: list[dict], msg_count_since_reflect: int) -> int:
        if self._reflexion is None:
            return msg_count_since_reflect
        if msg_count_since_reflect < self._reflect_interval:
            return msg_count_since_reflect
        if len(messages) < 2:
            return msg_count_since_reflect

        self._reflect_and_consolidate(messages, force=False)
        return 0

    def force_run(self, messages: list[dict]) -> None:
        if self._reflexion is None:
            return
        self._reflect_and_consolidate(messages, force=True)

    def _reflect_and_consolidate(self, messages: list[dict], force: bool = False) -> None:
        if self._reflexion is None:
            return
        try:
            result = self._reflexion.quick_reflect(messages)

            if self._memory:
                if result.get("speech_style"):
                    self._memory.add_semantic_by_type(
                        entry_type="trait",
                        content=f"Iris’s speech style: {result['speech_style']}",
                        tags=["speech_style"],
                    )
                if result.get("expressed_traits"):
                    self._memory.add_semantic_by_type(
                        entry_type="trait",
                        content=f"Iris’s personality traits: {result['expressed_traits']}",
                        tags=["personality_trait"],
                    )
                if result.get("user_reaction"):
                    self._memory.add_semantic_by_type(
                        entry_type="preference",
                        content=f"User reaction tendency: {result['user_reaction']}",
                        tags=["user_reaction"],
                    )

            if self._persona_profile is not None:
                self._persona_profile.update_from_reflection(result)

            if self._big_five is not None:
                bf_raw = result.get("big_five_estimate")
                estimate = self._parse_big_five_estimate(bf_raw)
                if estimate:
                    changes = self._big_five.update_from_estimate(estimate)
                    if changes and self._event_bus is not None:
                        self._event_bus.publish(
                            DebugSnapshotEvent(
                                timestamp=None,
                                source="hippocampal",
                                category="personality.big_five",
                                data=self._big_five.get_state(),
                                trigger="reflection",
                            )
                        )
                    if changes:
                        logger.info("Big Five updated: %s", changes)

            self._consolidate_short_term(force=force)

            logger.info(
                "Quick reflect stored: speech_style=%s traits=%s reaction=%s",
                bool(result.get("speech_style")),
                bool(result.get("expressed_traits")),
                bool(result.get("user_reaction")),
            )
        except Exception as e:
            logger.exception("Quick reflect failed: %s", e)

    def _parse_big_five_estimate(self, bf_raw: Any) -> dict[str, float] | None:
        if not bf_raw:
            return None
        if isinstance(bf_raw, dict):
            return bf_raw  # type: ignore[no-any-return]
        try:
            estimate = json.loads(bf_raw)
            if isinstance(estimate, dict):
                return estimate  # type: ignore[no-any-return]
        except (json.JSONDecodeError, TypeError):
            logger.debug("Could not parse big_five_estimate: %s", bf_raw)
        return None

    def _consolidate_short_term(self, force: bool = False) -> None:
        if self._memory is None:
            return
        if not force and not self._memory.short_term.should_consolidate():
            return
        unconsolidated = self._memory.short_term.get_unconsolidated_turns()
        if not unconsolidated:
            return
        user_turns = [t for t in unconsolidated if t.get("role") == "user"]
        if user_turns:
            combined = " | ".join(t["content"][:100] for t in user_turns[-3:])
            self._memory.long_term.store_episodic(
                {"content": f"[conversation] {combined}", "kind": "conversation"},
            )
        topics = self._memory.short_term.current_topics
        for topic in topics:
            self._memory.long_term.store_semantic(
                {"content": topic, "type": "topic", "tags": ["short_term_topic"]},
            )
        self._memory.short_term.mark_consolidated()
        logger.info("Hippocampal: consolidated %d turns, %d topics", len(unconsolidated), len(topics))

    def run_session(self, messages: list[dict], memory: MemoryManagerProtocol | None = None) -> None:
        if self._reflexion is None:
            return
        if len(messages) < 2:
            return

        mem = memory or self._memory
        if not mem:
            return

        try:
            result = self._reflexion.reflect(messages)
            if result.get("summary"):
                mem.add_episodic(
                    content=f"[session summary] {result['summary']}",
                    kind="system",
                )
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
