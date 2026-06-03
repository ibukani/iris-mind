from __future__ import annotations

from typing import Any

from loguru import logger

from iris.agency.planning.context.episodic import EpisodicProvider
from iris.agency.planning.context.participants import ParticipantsProvider
from iris.agency.planning.context.random_memory import RandomMemoryProvider
from iris.agency.planning.context.randomizer import SeedableRandom
from iris.agency.planning.context.semantic import SemanticProvider
from iris.agency.planning.context.user_preferences import UserPreferencesProvider
from iris.agency.planning.context.working_memory import WorkingMemoryProvider
from iris.agency.planning.utils import build_time_label
from iris.memory.manager import MemoryManager


class ContextHintBuilder:
    """文脈ヒントを構築する。各メモリ種別のプロバイダーを内包し、集約する。"""

    def __init__(self, memory: MemoryManager | None = None) -> None:
        self._memory = memory
        if memory:
            self._working_memory = WorkingMemoryProvider(memory)
            self._episodic = EpisodicProvider(memory)
            self._semantic = SemanticProvider(memory)
            self._participants = ParticipantsProvider(memory)
            self._user_prefs = UserPreferencesProvider(memory)
            self._random_memory = RandomMemoryProvider(memory)

    def build_proactive_context_hint(
        self,
        context: dict[str, Any],
        scores: dict[str, float],
        chaos_level: float = 0.0,
        room_id: str = "",
    ) -> str:
        if "system_event" in context:
            event_name = context.get("system_event")
            offline_duration = context.get("offline_duration", "")
            role = context.get("role", "")
            if event_name == "connected":
                if offline_duration:
                    return f"システムイベント: ロール {role} が {offline_duration} の切断期間を経て再接続しました。"
                return f"システムイベント: ロール {role} が接続しました。"
            return ""
        return self._build_general_hint(scores, context, chaos_level=chaos_level, room_id=room_id)

    def _build_general_hint(
        self, scores: dict[str, float], context: dict[str, Any], chaos_level: float = 0.0, room_id: str = ""
    ) -> str:
        if not self._memory:
            trigger = max(scores, key=lambda k: scores[k])
            return f"時間帯: {build_time_label()} / トリガー: {trigger}"

        parts: list[str] = []
        trigger = max(scores, key=lambda k: scores[k])
        parts.append(f"時間帯: {build_time_label()}")
        parts.append(f"トリガー: {trigger}")

        wc = self._working_memory.build(room_id=room_id)
        if wc:
            parts.append("ワーキングメモリ:\n" + wc)

        pref_ctx = self._user_prefs.build(room_id=room_id)
        if pref_ctx:
            parts.append(pref_ctx)

        if chaos_level > 0 and SeedableRandom.default().random() < chaos_level * 0.3:
            random_hint = self._random_memory.build()
            if random_hint:
                parts.append(random_hint)

        return " / ".join(parts)

    def build_user_context_hint(self, content: str, chaos_level: float = 0.0, room_id: str = "") -> str:
        if not self._memory or not content:
            return ""
        parts: list[str] = []
        try:
            wc = self._working_memory.build(query=content, room_id=room_id)
            if wc:
                parts.append(wc)
            else:
                ep_hint = self._episodic.build(room_id=room_id)
                if ep_hint:
                    parts.append(ep_hint)

            sem_hint = self._semantic.build(content, room_id=room_id)
            if sem_hint:
                parts.append(sem_hint)

            participant_hint = self._participants.build(room_id)
            if participant_hint:
                parts.append(participant_hint)

            if chaos_level > 0 and SeedableRandom.default().random() < chaos_level * 0.2:
                random_hint = self._random_memory.build()
                if random_hint:
                    parts.append(random_hint)
        except Exception:
            logger.debug("User context hint failed", exc_info=True)
        return " / ".join(parts)

    def build_user_preferences_context(self, room_id: str = "", account_id: str = "") -> str | None:
        if not self._memory:
            return None
        return self._user_prefs.build(room_id=room_id, account_id=account_id)
