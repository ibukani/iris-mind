from __future__ import annotations

from datetime import UTC, datetime
import time
from typing import TYPE_CHECKING, Any

from iris.memory.manager import MemoryManager

if TYPE_CHECKING:
    from iris.agency.inhibition import InhibitionController

from loguru import logger


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

    @staticmethod
    def build_ignore_context(ignore_count: int) -> str | None:
        if ignore_count < 1:
            return None
        return f"呼びかけに応答なし: {ignore_count}回"

    @staticmethod
    def build_timing_context(last_proactive_time: float, last_user_activity: float) -> list[str]:
        parts: list[str] = []
        if last_proactive_time > 0:
            elapsed = time.time() - last_proactive_time
            parts.append(f"直前出力: {int(elapsed)}秒前")
        if last_user_activity > 0:
            elapsed = time.time() - last_user_activity
            if elapsed < 60:
                parts.append("最終ユーザー入力: たった今")
            else:
                parts.append(f"最終ユーザー入力: {int(elapsed // 60)}分前")
        else:
            parts.append("最終ユーザー入力: --")
        return parts

    @staticmethod
    def build_frequency_context(outputs_since_input: int, frequency_exceeded: bool) -> list[str]:
        parts: list[str] = []
        if outputs_since_input >= 2:
            parts.append(f"出力: {outputs_since_input}回連続")
        if frequency_exceeded:
            parts.append("出力頻度高")
        return parts

    @staticmethod
    def build_mood_context(negative_mood_score: float) -> str | None:
        if negative_mood_score > 0.3:
            return "気分: 不機嫌"
        if negative_mood_score > 0.1:
            return "気分: やや不機嫌"
        return None

    def build_proactive_context_hint(
        self,
        context: dict[str, Any],
        scores: dict[str, float],
        inhibition: InhibitionController | None = None,
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
        return self._build_general_hint(scores, inhibition)

    def _build_general_hint(
        self,
        scores: dict[str, float],
        inhibition: InhibitionController | None = None,
    ) -> str:
        ignore_count = inhibition.consecutive_ignores if inhibition else 0
        last_activity = inhibition.last_user_activity if inhibition else 0.0
        last_proactive = inhibition.last_proactive_time if inhibition else 0.0
        mood_score = inhibition.negative_mood_score if inhibition else 0.0
        outputs = inhibition.outputs_since_input if inhibition else 0
        freq_exceeded = inhibition.frequency_exceeded if inhibition else False

        parts: list[str] = []
        trigger = max(scores, key=lambda k: scores[k])

        ignore_ctx = ContextHintBuilder.build_ignore_context(ignore_count)
        if ignore_ctx:
            parts.append(ignore_ctx)

        parts.extend(ContextHintBuilder.build_timing_context(last_proactive, last_activity))
        parts.extend(ContextHintBuilder.build_frequency_context(outputs, freq_exceeded))

        mood_ctx = ContextHintBuilder.build_mood_context(mood_score)
        if mood_ctx:
            parts.append(mood_ctx)

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
