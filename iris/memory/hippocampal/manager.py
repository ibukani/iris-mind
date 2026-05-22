from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

import orjson

if TYPE_CHECKING:
    from iris.limbic.big_five import BigFiveProfile
    from iris.memory.manager import MemoryManagerProtocol
    from iris.memory.persona_profile import PersonaProfile

from loguru import logger

from iris.event.event_types import DebugSnapshotEvent, InputReady, InterruptEvent
from iris.memory.hippocampal.reflexion import ReflexionProtocol

_REFLECTION_MEMORY_KEYS: list[tuple[str, str, str, list[str]]] = [
    ("speech_style", "trait", "Iris's speech style", ["speech_style"]),
    ("expressed_traits", "trait", "Iris's personality traits", ["personality_trait"]),
    ("user_reaction", "preference", "User reaction tendency", ["user_reaction"]),
]


class HippocampalManagerProtocol(Protocol):
    """海馬マネージャーのインターフェース。

    なぜこの設計にしたか:
    短期記憶から長期記憶への定着（コンソリデーション）および省察処理をモック化または
    別のアプローチで差し替え可能にし、テスト容易性と柔軟性を向上させるため。
    """

    def maybe_run(self, messages: list[dict], msg_count_since_reflect: int) -> int: ...
    def force_run(self, messages: list[dict]) -> None: ...
    def run_session(self, messages: list[dict], memory: MemoryManagerProtocol | None = None) -> None: ...
    def process_proactive_result(self, topic: str, success: bool, content: str) -> None: ...


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
            self._store_reflection_to_memory(result)
            if self._persona_profile is not None:
                self._persona_profile.update_from_reflection(result)
            self._update_big_five(result)
            self._consolidate_short_term(force=force)
            logger.info(
                "Quick reflect stored: speech_style=%s traits=%s reaction=%s",
                bool(result.get("speech_style")),
                bool(result.get("expressed_traits")),
                bool(result.get("user_reaction")),
            )
        except Exception as e:
            logger.exception("Quick reflect failed: %s", e)

    def _store_reflection_to_memory(self, result: dict[str, Any]) -> None:
        if self._memory is None:
            return
        for key, entry_type, prefix, tags in _REFLECTION_MEMORY_KEYS:
            val = result.get(key)
            if val:
                self._memory.add_semantic_by_type(
                    entry_type=entry_type,
                    content=f"{prefix}: {val}",
                    tags=tags,
                )

        new_goals = result.get("new_goals")
        if new_goals and isinstance(new_goals, list):
            for goal_desc in new_goals:
                if isinstance(goal_desc, str) and goal_desc.strip():
                    self._memory.goals.add_goal(description=goal_desc, weight=1.0)

    def _update_big_five(self, result: dict[str, Any]) -> None:
        if self._big_five is None:
            return
        bf_raw = result.get("big_five_estimate")
        estimate = self._parse_big_five_estimate(bf_raw)
        if not estimate:
            return
        changes = self._big_five.update_from_estimate(estimate)
        if not changes:
            return
        if self._event_bus is not None:
            self._event_bus.publish(
                DebugSnapshotEvent(
                    timestamp=None,
                    source="hippocampal",
                    category="personality.big_five",
                    data=self._big_five.get_state(),
                    trigger="reflection",
                )
            )
        logger.info("Big Five updated: %s", changes)

    def _parse_big_five_estimate(self, bf_raw: Any) -> dict[str, float] | None:
        if not bf_raw:
            return None
        if isinstance(bf_raw, dict):
            return bf_raw  # type: ignore[no-any-return]
        try:
            estimate = orjson.loads(bf_raw.encode("utf-8"))
            if isinstance(estimate, dict):
                return estimate  # type: ignore[no-any-return]
        except (orjson.JSONDecodeError, TypeError):
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

            new_goals = result.get("new_goals")
            if new_goals and isinstance(new_goals, list):
                for goal_desc in new_goals:
                    if isinstance(goal_desc, str) and goal_desc.strip():
                        mem.goals.add_goal(description=goal_desc, weight=1.0)

            new_interests = result.get("new_interests")
            if new_interests and isinstance(new_interests, list) and self._persona_profile is not None:
                for topic in new_interests:
                    if isinstance(topic, str) and topic.strip():
                        self._persona_profile.persona_data.add_interest(topic.strip(), 0.3)

            logger.info("Session reflect completed")
        except Exception as e:
            logger.exception("Session reflect failed: %s", e)

    def process_proactive_result(self, topic: str, success: bool, content: str) -> None:
        if self._persona_profile is None or not topic:
            return

        satisfaction = 0.0
        summary = "調査に失敗しました。"
        next_interests = []

        if success and self._reflexion is not None:
            try:
                if hasattr(self._reflexion, "evaluate_proactive_result"):
                    eval_res = self._reflexion.evaluate_proactive_result(topic, content)
                    satisfaction = eval_res.get("satisfaction", 0.0)
                    summary = eval_res.get("summary", "")
                    next_interests = eval_res.get("next_interests", [])
            except Exception as e:
                logger.exception("Failed to evaluate proactive result with LLM: %s", e)

        # 納得度評価に基づく減衰/維持
        delta = -0.3 if satisfaction >= 0.7 else 0.1

        self._persona_profile.persona_data.add_interest(topic, delta)

        for next_topic in next_interests:
            if isinstance(next_topic, str) and next_topic.strip():
                self._persona_profile.persona_data.add_interest(next_topic.strip(), 0.3)

        if self._memory is not None:
            outcome = "成功" if success else "失敗"
            self._memory.add_episodic(
                content=f"[self investigation] {topic} について調査（結果: {outcome}）。まとめ: {summary}",
                kind="system",
            )

        if success and satisfaction >= 0.7 and self._event_bus is not None:
            import random

            if random.random() < 0.5:
                logger.info("Escalating proactive result to user conversation for topic: %s", topic)

                self._event_bus.publish(
                    InterruptEvent(
                        timestamp=None,
                        source="hippocampal",
                        session_id="",
                    )
                )
                self._event_bus.publish(
                    InputReady(
                        timestamp=None,
                        source="hippocampal",
                        session_id="",
                        content="",
                        context={
                            "escalation": True,
                            "topic": topic,
                            "summary": summary,
                        },
                    )
                )
