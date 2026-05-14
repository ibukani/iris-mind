"""
ConversationService — 会話処理パイプライン。

アダプター層から process_input() で呼び出され、LLM 応答を生成 → AgentResponseEvent を発行する。
LLM呼び出し・ツールループ・Reflexionはそれぞれ LLMPipeline / ReflexionManager に委譲。
"""

from __future__ import annotations

import logging
from datetime import datetime

from .context import ContextManager
from .event_bus import AgentResponseEvent, AgentStreamEvent, EventBus
from .llm_pipeline import LLMPipeline
from .reflexion_manager import ReflexionManager

logger = logging.getLogger(__name__)


class ConversationService:
    """
    会話処理サービス。

    process_input() で呼び出され、以下のフローを実行する：
    1. LLMPipeline で LLM 呼び出し（システムプロンプト構築 + tool loop）
    2. AgentResponseEvent 発行
    3. ReflexionManager で Nターンごとの quick_reflect
    4. ContextManager で compaction
    """

    def __init__(
        self,
        event_bus: EventBus,
        llm_pipeline: LLMPipeline,
        reflexion_manager: ReflexionManager | None = None,
        context_manager: ContextManager | None = None,
        context_window: int = 0,
    ) -> None:
        self._event_bus = event_bus
        self._llm_pipeline = llm_pipeline
        self._reflexion_manager = reflexion_manager
        self._context_manager = context_manager
        self._context_window = context_window
        self._messages: list[dict] = []
        self._msg_count_since_reflect: int = 0

    # ── 公開API ───────────────────────────────────────────

    def process_input(self, content: str) -> None:
        """ユーザー入力を処理する。（ストリーミング対応）
        コマンド（/ で始まる入力）は CommandRouter が処理するため、本メソッドでは扱わない。"""
        if content.startswith("/"):
            return
        self._messages.append({"role": "user", "content": content})

        # Thinking 開始通知
        self._event_bus.publish(
            AgentStreamEvent(
                timestamp=datetime.now(),
                source="assistant",
                delta="",
            )
        )

        try:
            response_text = self._llm_pipeline.iterate_with_tools(
                self._messages,
                on_token=lambda delta: self._event_bus.publish(
                    AgentStreamEvent(
                        timestamp=datetime.now(),
                        source="assistant",
                        delta=delta,
                    )
                ),
            )
        except Exception as e:
            response_text = f"[Error: {e}]"
            logger.exception("LLM call failed")

        self._messages.append({"role": "assistant", "content": response_text})

        # ストリーム完了通知
        self._event_bus.publish(
            AgentStreamEvent(
                timestamp=datetime.now(),
                source="assistant",
                delta="",
                done=True,
            )
        )
        self._event_bus.publish(
            AgentResponseEvent(
                timestamp=datetime.now(),
                source="assistant",
                content=response_text,
            )
        )

        self._msg_count_since_reflect += 1
        self._maybe_quick_reflect()
        self._maybe_compact()

    # ── Reflexion ────────────────────────────────────────

    def _maybe_quick_reflect(self) -> None:
        """Nターンごとに quick_reflect を実行する。"""
        if self._reflexion_manager is None:
            return
        self._msg_count_since_reflect = self._reflexion_manager.maybe_run(
            self._messages,
            self._msg_count_since_reflect,
        )

    def session_reflect(self) -> None:
        """セッション終了時に full reflect を実行する。"""
        if self._reflexion_manager is None:
            return
        self._reflexion_manager.run_session(self._messages)

    # ── コンパクション ───────────────────────────────────

    def _maybe_compact(self) -> None:
        """トークン数が閾値を超えた場合、会話履歴を要約する。"""
        if self._context_manager is None or self._context_window <= 0:
            return
        self._context_manager.check_and_summarize(
            self._messages,
            context_window=self._context_window,
        )

    def force_compact(self) -> None:
        """会話履歴を強制要約する。"""
        if self._context_manager is None or len(self._messages) < 2:
            return
        self._context_manager.force_summarize(self._messages)
        logger.info("Conversation force compacted")

    # ── 会話履歴管理 ─────────────────────────────────────

    def clear_history(self) -> None:
        """会話履歴をクリアする。"""
        self._messages.clear()
        self._msg_count_since_reflect = 0
        if self._context_manager is not None:
            self._context_manager.clear()
        logger.info("Conversation history cleared")
