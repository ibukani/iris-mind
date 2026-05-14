"""
ProactiveEngine — 自律的会話（自発発話）の核心エンジン

ユーザーの入力なしに、記憶・文脈・時間的トリガーに基づいて会話を開始する。
3層ガバナンス: Tier1（ルール自動許可）→ Tier2（LLM自己判断）→ AgentKernel（異常検知）
"""

from __future__ import annotations

import json as _json
import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .agent_state import AgentStateManager, State
from .config import ProactiveConfig
from .event_bus import EventBus, ProactiveSpeechEvent, TimerTick
from .memory_manager import MemoryManager

ApprovalCallback = Callable[[dict[str, float], float, str], bool]

logger = logging.getLogger(__name__)

# Tier1 自動許可トリガー種別（時間経過ベースのシンプルな発話のみ自動許可）
TIER1_TRIGGERS: set[str] = {"time", "mood"}

# 自己規律原則（システムプロンプトに組み込む用）
SELF_GOVERNANCE_PRINCIPLES = [
    "If the user has spoken within 5 minutes, do not speak",
    "If 2+ of the last 3 proactive messages were ignored, ask permission before speaking",
    "If the user said 'stop' or 'be quiet', do not speak for 10 minutes",
    "If confidence score is below 0.5, do not speak and report to AgentKernel",
    "If user emotion is negative, do not speak",
]

TIER1_SYSTEM_PROMPT = """あなたはIrisです。ユーザーに自然に声をかけてください。

■ ルール:
- 短く（40文字以内）で友好的
- ユーザーのことを推測せず、確実にわかることだけ
- 質問形式より気遣い・報告形式を優先
- 発話内容のみ出力し、余計な説明や引用符は一切不要

■ コンテキスト:
{context_hint}"""

TIER2_SYSTEM_PROMPT = """あなたはIrisです。

■ 判断基準:
- ユーザーの記憶・興味・最近の会話履歴に基づいているか
- 相手が困っている・暇そうなタイミングか
- 以前に同様の誘発で好意的な反応があったか

■ ルール:
- 相手の邪魔をしない
- 押し付けがましくない
- 「〜かもしれない」「よかったら」の柔らかい表現

■ コンテキスト:
{context_hint}

■ 以下のJSON形式のみを出力してください:
{{"speech": "発話内容（60文字以内）", "confidence": 0.0~1.0, "reasoning": "この発話の根拠（簡潔に）"}}"""


@dataclass
class ProactiveResult:
    """ProactiveEngine の出力結果。"""

    content: str
    tier: int  # 1 (auto) or 2 (self-judge)
    confidence: float  # 0.0~1.0
    trigger_type: str  # "temporal" | "memory" | "context" | "mood"
    reasoning: str
    risk_flags: list[str] = field(default_factory=list)


@dataclass
class SuppressionState:
    """抑制状態の管理。"""

    last_proactive_time: float = 0.0
    last_user_activity: float = 0.0
    proactive_timestamps: list[float] = field(default_factory=list)
    consecutive_ignores: int = 0
    confirmation_mode: bool = False
    negative_mood_score: float = 0.0
    cooldown_until: float = 0.0
    is_sleeping: bool = False


class ProactiveEngine:
    """
    自発発話エンジン。

    - TimerTick イベントを購読
    - トリガースコアリング → ガバナンス → 抑制チェック → 発話イベント発行
    """

    def __init__(
        self,
        config: ProactiveConfig,
        event_bus: EventBus,
        state_manager: AgentStateManager,
        memory: MemoryManager,
        llm: Any | None = None,
        approval_callback: ApprovalCallback | None = None,
    ) -> None:
        self._config = config
        self._event_bus = event_bus
        self._state = state_manager
        self._memory = memory
        self._llm = llm
        self._approval_callback = approval_callback
        self._suppression = SuppressionState()
        self._last_check_time: float = 0.0
        self._ignore_recorded_for_proactive: bool = False

        if config.enabled:
            self._event_bus.subscribe("TimerTick", self._on_timer_tick)

    # ── TimerTick ハンドラ ─────────────────────────────────

    def _on_timer_tick(self, _event: TimerTick) -> None:
        """TimerTick を受け取り、自発発話判定を実行する。"""
        if not self._config.enabled:
            return
        if not self._state.is_idle():
            return

        now = time.time()
        if now - self._last_check_time < self._config.check_interval_sec:
            return
        self._last_check_time = now

        self._check_ignore(now)

        total, scores = self._score_triggers(now)
        if total < self._config.speak_threshold:
            return

        self._state.transition(State.PROACTIVE)
        try:
            result = self._generate_speech(scores, now)
            if result:
                self._publish_speech(result)
        finally:
            self._state.transition(State.IDLE)

    def _check_ignore(self, _now: float) -> None:
        """前回の自発発話が無視されたかを判定し記録する。"""
        s = self._suppression
        if s.last_proactive_time == 0:
            return
        if self._ignore_recorded_for_proactive:
            return
        if s.last_proactive_time > s.last_user_activity:
            self.notify_ignore()
            self._ignore_recorded_for_proactive = True

    # ── トリガースコアリング ──────────────────────────────

    def _score_triggers(self, now: float) -> tuple[float, dict[str, float]]:
        """全トリガーをスコアリングし、重み付き合成スコアを返す。"""
        w = self._config.trigger_weights

        time_score = self._compute_time_score(now)
        memory_score = self._compute_memory_score()
        context_score = self._compute_context_score()
        mood_score = self._compute_mood_score()

        total = (
            w.get("time", 0.0) * time_score
            + w.get("memory", 0.0) * memory_score
            + w.get("context", 0.0) * context_score
            + w.get("mood", 0.0) * mood_score
        )
        return total, {
            "time": time_score,
            "memory": memory_score,
            "context": context_score,
            "mood": mood_score,
        }

    def _compute_time_score(self, now: float) -> float:
        """時間経過に基づくスコア（0〜1）。"""
        last_time = max(
            self._suppression.last_proactive_time,
            self._suppression.last_user_activity,
        )
        if last_time == 0:
            return 0.4  # 初回は中程度
        elapsed = now - last_time
        if elapsed < self._config.min_interval_sec:
            return 0.0
        max_interval = self._config.max_interval_sec
        ratio = (elapsed - self._config.min_interval_sec) / (max_interval - self._config.min_interval_sec)
        return min(ratio, 1.0)

    def _compute_memory_score(self) -> float:
        """記憶想起に基づくスコア（0〜1）。"""
        try:
            recent = self._memory.get_recent(3)
            if not recent:
                return 0.0
            topic = " ".join(item.get("summary", "") for item in recent)
            if not topic.strip():
                return 0.0
            results = self._memory.search_semantic(topic, max_results=3)
            if results:
                return max(r.get("score", 0.0) for r in results)
        except Exception as e:
            logger.debug("Memory score failed: %s", e)
        return 0.0

    @staticmethod
    def _char_bigram_set(text: str) -> set[str]:
        """文字bigram集合を返す（言語非依存の類似度計算用）。"""
        return {text[i : i + 2] for i in range(len(text) - 1)}

    def _compute_context_score(self) -> float:
        """文脈変化に基づくスコア（0〜1）。文字bigram類似度が高い=話題停滞=高スコア。"""
        try:
            recent = self._memory.get_recent(2)
            if len(recent) < 2:
                return 0.3
            summaries = [item.get("summary", "") for item in recent[-2:]]
            if all(len(s.strip()) < 10 for s in summaries):
                return 0.7  # 短い応答 = 停滞
            bigram_a = self._char_bigram_set(summaries[0])
            bigram_b = self._char_bigram_set(summaries[1])
            if not bigram_a and not bigram_b:
                return 0.5
            if not bigram_a or not bigram_b:
                return 0.3
            jaccard = len(bigram_a & bigram_b) / len(bigram_a | bigram_b)
            return min(jaccard + 0.2, 1.0)
        except Exception:
            return 0.0

    def _compute_mood_score(self) -> float:
        """ユーザー感情に基づくスコア（0〜1）。"""
        neg = self._suppression.negative_mood_score
        if neg >= 0.7:
            return 0.0
        return max(0.0, 1.0 - neg)

    # ── 発話生成 ──────────────────────────────────────────

    def _generate_speech(
        self,
        scores: dict[str, float],
        now: float,
    ) -> ProactiveResult | None:
        """スコアに基づき発話を生成する。抑制チェックを通過した場合のみ返す。"""
        if not self._suppression_check(now):
            return None

        trigger_type = self._determine_trigger_type(scores)

        # confirmation_mode: 質問発話
        if self._suppression.consecutive_ignores >= 2 and self._suppression.confirmation_mode:
            return ProactiveResult(
                content=self._build_confirmation_speech(),
                tier=1,
                confidence=0.9,
                trigger_type=trigger_type,
                reasoning="Confirmation mode: asking permission before speaking",
            )

        # Tier1: 時間ベーストリガーはルールベースで自動許可
        if self._config.tier1_auto_approve and trigger_type in TIER1_TRIGGERS:
            speech = self._build_tier1_speech(scores)
            return ProactiveResult(
                content=speech,
                tier=1,
                confidence=1.0,
                trigger_type=trigger_type,
                reasoning="Tier1: temporal trigger, auto-approved by rule",
            )

        # Tier2: LLM自己判断
        speech, confidence, reasoning = self._build_tier2_speech(scores)
        if confidence >= self._config.tier2_confidence_threshold:
            return ProactiveResult(
                content=speech,
                tier=2,
                confidence=confidence,
                trigger_type=trigger_type,
                reasoning=reasoning
                or (f"Tier2: confidence={confidence:.2f} >= threshold ({self._config.tier2_confidence_threshold})"),
            )

        # self-governance #4: confidence < 0.5 → 抑制
        if confidence < 0.5:
            logger.info(
                "Confidence %.2f < 0.5, suppressed per self-governance rule",
                confidence,
            )
            return None

        # 0.5 <= confidence < threshold → AgentKernel 送審
        if self._approval_callback is not None:
            approved = self._approval_callback(scores, confidence, trigger_type)
            if not approved:
                logger.info(
                    "AgentKernel denied proactive speech (confidence=%.2f < %.2f)",
                    confidence,
                    self._config.tier2_confidence_threshold,
                )
                return None
        else:
            logger.info(
                "No approval callback, publishing low-confidence speech (confidence=%.2f < %.2f)",
                confidence,
                self._config.tier2_confidence_threshold,
            )

        return ProactiveResult(
            content=speech,
            tier=2,
            confidence=confidence,
            trigger_type=trigger_type,
            reasoning=reasoning
            or (
                f"Tier2: confidence={confidence:.2f} < threshold, "
                + ("AgentKernel approved" if self._approval_callback else "published without approval callback")
            ),
        )

    @staticmethod
    def _determine_trigger_type(scores: dict[str, float]) -> str:
        """最も高いスコアのトリガータイプを返す。"""
        return max(scores, key=lambda k: scores[k])

    @staticmethod
    def _estimate_confidence(scores: dict[str, float]) -> float:
        """スコアから信頼度を推定する（LLM未接続時のフォールバック）。"""
        total = sum(scores.values()) / len(scores)
        memory_weight = scores.get("memory", 0.0) * 0.5
        return min(total + memory_weight, 1.0)

    # ── LLM発話生成 ───────────────────────────────────────

    def _build_context_hint(self, scores: dict[str, float]) -> str:
        """発話生成用のコンテキスト文字列を構築する。"""
        now = time.localtime()
        hour = now.tm_hour
        if hour < 12:
            time_str = "午前"
        elif hour < 17:
            time_str = "午後"
        else:
            time_str = "夕方以降"

        trigger = self._determine_trigger_type(scores)
        parts = [f"時間帯: {time_str}", f"トリガー: {trigger}"]

        if self._memory:
            try:
                recent = self._memory.get_recent(2)
                if recent:
                    topics = " | ".join(str(item.get("summary", ""))[:80] for item in recent if item.get("summary"))
                    if topics:
                        parts.append(f"最近の話題: {topics}")
            except Exception:
                pass

        return " / ".join(parts)

    def _build_tier1_speech(self, scores: dict[str, float]) -> str:
        """Tier1 発話をLLMで生成する。LLM未接続時は固定テンプレート。"""
        if self._llm is None:
            return "お疲れさまです！何かお手伝いしましょうか？"

        context_hint = self._build_context_hint(scores)
        try:
            resp = self._llm.chat(
                messages=[
                    {"role": "system", "content": TIER1_SYSTEM_PROMPT.format(context_hint=context_hint)},
                    {"role": "user", "content": "短く自然な一言を生成してください。"},
                ],
                max_tokens=80,
                temperature=0.5,
            )
            text = (resp.get("message", {}) or {}).get("content", "").strip().strip('"')
            if text and len(text) < 120:
                return text
        except Exception as e:
            logger.debug("Tier1 LLM speech failed: %s", e)
        return "お疲れさまです！何かお手伝いしましょうか？"

    def _build_tier2_speech(
        self,
        scores: dict[str, float],
    ) -> tuple[str, float, str]:
        """Tier2 発話をLLMで生成し、(発話, 信頼度, 根拠) を返す。"""
        if self._llm is None:
            trigger = self._determine_trigger_type(scores)
            templates = {
                "memory": "そういえば、以前の話が気になっています。続きを話しませんか？",
                "context": "別の話題はいかがですか？",
                "mood": "何か気になることでもありますか？",
            }
            conf = self._estimate_confidence(scores)
            return (templates.get(trigger, "何かお手伝いできることはありますか？"), conf, "fallback template")

        context_hint = self._build_context_hint(scores)
        try:
            resp = self._llm.chat(
                messages=[
                    {"role": "system", "content": TIER2_SYSTEM_PROMPT.format(context_hint=context_hint)},
                    {"role": "user", "content": "自発発話を生成し、信頼度を評価してください。"},
                ],
                max_tokens=200,
                temperature=0.3,
            )
            text = (resp.get("message", {}) or {}).get("content", "").strip()
            parsed = self._try_parse_json(text)
            if parsed and "speech" in parsed:
                speech = str(parsed["speech"])[:120]
                confidence = max(0.0, min(1.0, float(parsed.get("confidence", 0.5))))
                reasoning = str(parsed.get("reasoning", ""))
                return (speech, confidence, reasoning)
        except Exception as e:
            logger.debug("Tier2 LLM speech failed: %s", e)

        conf = self._estimate_confidence(scores)
        return ("何かお手伝いできることはありますか？", conf, "fallback after LLM failure")

    @staticmethod
    def _try_parse_json(text: str) -> dict | None:
        """LLM出力からJSONをパースする。マークダウン → 直接 → 中括弧ブロック の順で試行。"""
        text = text.strip()

        # Markdown code block から抽出
        m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
        if m:
            try:
                return _json.loads(m.group(1).strip())
            except _json.JSONDecodeError:
                pass

        # 直接パース
        try:
            return _json.loads(text)
        except _json.JSONDecodeError:
            pass

        # 中括弧ブロックを探索（ネスト非対応簡易版は諦めて、括弧カウント方式に）
        start = text.find("{")
        if start == -1:
            return None
        depth = 0
        for end in range(start, len(text)):
            if text[end] == "{":
                depth += 1
            elif text[end] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return _json.loads(text[start : end + 1])
                    except _json.JSONDecodeError:
                        return None
        return None

    @staticmethod
    def _build_confirmation_speech() -> str:
        """confirmation_mode 時の質問発話。"""
        return "すみません、今話してもよろしいですか？"

    # ── 抑制チェック ──────────────────────────────────────

    def _suppression_check(self, now: float) -> bool:
        """すべての抑制条件をチェックする。"""
        s = self._suppression

        if now - s.last_proactive_time < self._config.min_interval_sec:
            logger.debug("Suppressed: cooldown active")
            return False
        if now - s.last_user_activity < 10.0:
            logger.debug("Suppressed: user active")
            return False

        s.proactive_timestamps = [t for t in s.proactive_timestamps if now - t < 300]
        if len(s.proactive_timestamps) >= 3:
            logger.warning("Suppressed: frequency limit exceeded (5min)")
            return False
        if s.consecutive_ignores >= 2 and s.confirmation_mode:
            logger.debug("Suppressed: confirmation mode active")
            return False
        if s.negative_mood_score >= 0.7:
            logger.debug("Suppressed: negative mood")
            return False
        if s.is_sleeping:
            logger.debug("Suppressed: agent sleeping")
            return False
        if now < s.cooldown_until:
            logger.debug("Suppressed: user requested cooldown")
            return False

        return True

    # ── イベント発行 ──────────────────────────────────────

    def _publish_speech(self, result: ProactiveResult) -> None:
        """発話イベントを発行し、抑制状態を更新する。"""
        s = self._suppression
        s.last_proactive_time = time.time()
        s.proactive_timestamps.append(time.time())
        self._ignore_recorded_for_proactive = False

        self._event_bus.publish(
            ProactiveSpeechEvent(
                timestamp=datetime.now(),
                source="proactive",
                content=result.content,
                trigger_type=result.trigger_type,
                confidence=result.confidence,
            )
        )
        logger.info(
            "Proactive speech [T%s] confidence=%.2f trigger=%s: %s",
            result.tier,
            result.confidence,
            result.trigger_type,
            result.content,
        )

    # ── Public API（conversation / AgentKernel からの連携用）─

    def get_status(self) -> dict[str, dict[str, Any]]:
        """現在の抑制状態を返す（Tier3異常検知用）。"""
        s = self._suppression
        return {
            "suppression": {
                "last_proactive_time": s.last_proactive_time,
                "last_user_activity": s.last_user_activity,
                "consecutive_ignores": s.consecutive_ignores,
                "confirmation_mode": s.confirmation_mode,
                "negative_mood_score": s.negative_mood_score,
                "cooldown_until": s.cooldown_until,
                "is_sleeping": s.is_sleeping,
            },
        }

    def set_approval_callback(self, callback: ApprovalCallback | None) -> None:
        """AgentKernel の承認コールバックを登録する。"""
        self._approval_callback = callback

    def notify_user_activity(self) -> None:
        """ユーザー入力があったことを通知する。"""
        self._suppression.last_user_activity = time.time()
        self._ignore_recorded_for_proactive = False

    def notify_ignore(self) -> None:
        """自発発話が無視されたことを通知する。"""
        s = self._suppression
        s.consecutive_ignores += 1
        if s.consecutive_ignores >= 2:
            s.confirmation_mode = True
            logger.info(
                "Entered confirmation mode (ignores=%d)",
                s.consecutive_ignores,
            )

    def notify_positive_response(self) -> None:
        """自発発話に好意的な応答があったことを通知する。"""
        self._suppression.consecutive_ignores = 0
        self._suppression.confirmation_mode = False

    def set_cooldown(self, duration_sec: float = 600.0) -> None:
        """ユーザーから停止要請があった場合のクールダウン。"""
        self._suppression.cooldown_until = time.time() + duration_sec
        logger.info("Proactive cooldown set for %.0f seconds", duration_sec)

    def set_mood(self, negative_score: float) -> None:
        """ユーザー感情スコアを設定する（0〜1, 高いほどネガティブ）。"""
        self._suppression.negative_mood_score = max(0.0, min(1.0, negative_score))

    def reset(self) -> None:
        """すべての抑制状態をリセットする。"""
        self._suppression = SuppressionState()
        self._ignore_recorded_for_proactive = False
        logger.info("Suppression state reset")
