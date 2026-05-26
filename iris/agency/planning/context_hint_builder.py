from __future__ import annotations

from datetime import UTC, datetime
import time
from typing import Any

from loguru import logger

from iris.memory.manager import MemoryManager


class ContextHintBuilder:
    def __init__(self, memory: MemoryManager | None = None) -> None:
        self._memory = memory

    @staticmethod
    def build_time_label() -> str:
        hour = time.localtime().tm_hour
        if hour < 12:
            return "午前"
        if hour < 17:
            return "午後"
        return "夕方以降"

    def build_proactive_context_hint(
        self,
        context: dict[str, Any],
        scores: dict[str, float],
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
        return self._build_general_hint(scores, context)

    def _build_general_hint(self, scores: dict[str, float], context: dict[str, Any]) -> str:
        parts: list[str] = []
        trigger = max(scores, key=lambda k: scores[k])
        parts.append(f"時間帯: {ContextHintBuilder.build_time_label()}")
        parts.append(f"トリガー: {trigger}")

        wc = self._build_working_context()
        if wc:
            parts.append("ワーキングメモリ:\n" + wc)

        pref_ctx = self.build_user_preferences_context()
        if pref_ctx:
            parts.append(pref_ctx)

        return " / ".join(parts)

    def build_user_context_hint(self, content: str) -> str:
        if not self._memory or not content:
            return ""
        parts: list[str] = []
        try:
            wc = self._build_working_context(query=content)
            if wc:
                parts.append(wc)
            else:
                ep_hint = self._build_episodic_hint()
                if ep_hint:
                    parts.append(ep_hint)

            sem_hint = self._build_semantic_hint(content)
            if sem_hint:
                parts.append(sem_hint)
        except Exception:
            logger.debug("User context hint failed", exc_info=True)
        return " / ".join(parts)

    def _build_working_context(self, query: str | None = None) -> str:
        if self._memory is None:
            return ""
        try:
            wm = self._memory.short_term.render_context(query=query)
            if wm:
                return wm
            recent = self._memory.get_recent(3)
            topics = [
                f"{e['summary'][:60]}（{self._format_age(e.get('timestamp', ''))}）" for e in recent if e.get("summary")
            ]
            if topics:
                return "直近の話題: " + " | ".join(topics)
        except Exception:
            logger.debug("Working context failed", exc_info=True)
        return ""

    def _build_episodic_hint(self) -> str | None:
        if not self._memory:
            return None
        recent = self._memory.get_recent(3)
        for e in reversed(recent):
            s = e.get("summary", "")
            if not s:
                continue
            ts = self._format_age(e.get("timestamp", ""))
            if ts:
                label = "直前の話題" if ts == "たった今" else "過去の話題"
                return f"{label}: {s[:60]}（{ts}）"
            return f"話題: {s[:60]}"
        return None

    def _build_semantic_hint(self, content: str) -> str | None:
        if not self._memory:
            return None
        results = self._memory.search_semantic(content, max_results=2)
        if not results:
            return None
        best = max(results, key=lambda r: r.get("score", 0))
        if best.get("score", 0) <= 0.5:
            return None
        ts = self._format_age(best.get("timestamp", ""))
        label = f"関連記憶: {best.get('content', '')[:60]}"
        if ts:
            label += f"（{ts}）"
        return label

    def build_user_preferences_context(self) -> str | None:
        if not self._memory:
            return None
        try:
            prefs = self._memory.get_user_preferences()
            if prefs:
                return f"ユーザーの関心: {prefs[0].get('content', '')[:80]}"
        except Exception:
            logger.debug("Memory hint failed", exc_info=True)
        return None

    @staticmethod
    def _format_age(ts: str) -> str:
        if not ts:
            return ""
        try:
            dt = datetime.fromisoformat(ts)
            diff = datetime.now(UTC) - dt
            secs = int(diff.total_seconds())
            if secs < 60:
                return "たった今"
            if secs < 3600:
                return f"{secs // 60}分前"
            if secs < 86400:
                return f"{secs // 3600}時間前"
            days = secs // 86400
            return f"{days}日前" if days > 1 else "昨日"
        except Exception:
            return ""
