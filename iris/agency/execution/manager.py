from __future__ import annotations

from collections.abc import Callable
import logging
import threading
import time
from typing import Any

from iris.agency.bus import InternalBus, PlanDecided
from iris.agency.execution.inhibition import InhibitionController
from iris.agency.execution.monitor import OutputMonitor
from iris.agency.execution.pipeline import LLMPipeline
from iris.event.event_bus import EventBus
from iris.event.event_types import MessageEvent, MonitorFeedback, TimerTick
from iris.io.models import StreamState
from iris.kernel.config import Config, ModelConfig
from iris.llm.context_window import LLMContextWindowManager
from iris.memory.hippocampal.manager import HippocampalManager
from iris.memory.manager import MemoryManager

logger = logging.getLogger(__name__)


class ExecutionManager:
    """意思決定されたプランに基づいてLLMの実行、出力監視、記憶の更新を統合管理するクラス。

    脳科学のアナロジー：
        - 運動野・基底核に対応し、行動（LLM Pipelineの実行、ツール実行）を担当。
    """

    def __init__(
        self,
        internal_bus: InternalBus,
        event_bus: EventBus,
        llm_pipeline: LLMPipeline,
        context_window_mgr: LLMContextWindowManager | None = None,
        context_window: int = 0,
        model_config: ModelConfig | None = None,
        hippocampal: HippocampalManager | None = None,
        monitor: OutputMonitor | None = None,
        inhibition: InhibitionController | None = None,
        session_roles_getter: Callable[[], str] | None = None,
        memory: MemoryManager | None = None,
        config: Config | None = None,
    ) -> None:
        self._bus = internal_bus
        self._event_bus = event_bus
        self._pipeline = llm_pipeline
        self._context_window_mgr = context_window_mgr
        self._context_window = context_window
        self._model_config = model_config
        self._hippocampal = hippocampal
        self._monitor = monitor
        self._inhibition = inhibition
        self._session_roles_getter = session_roles_getter
        self._memory = memory
        self._config = config
        self._messages: list[dict[str, Any]] = []
        self._msg_count_since_reflect = 0
        self._last_activity_time = time.time()
        self._reflect_lock = threading.Lock()
        self._is_reflecting = False
        self._bus.subscribe("PlanDecided", self._on_plan)
        self._event_bus.subscribe("TimerTick", self._on_timer_tick)

    def _on_plan(self, event: PlanDecided) -> None:
        """内部イベントバスからPlanDecidedを受信したときのコールバック。"""
        if self._monitor and event.plan.get("content", ""):
            self._monitor.record_user_input()

        if self._monitor:
            talkative = self._monitor.talkative_degree
            event.plan["talkative_degree"] = talkative
            if self._inhibition:
                self._inhibition.set_output_frequency_state(
                    self._monitor.outputs_since_last_input,
                    self._monitor.frequency_exceeded,
                )

            emotion = event.plan.get("current_emotion")
            if emotion:
                from iris.limbic.models import EmotionState

                if isinstance(emotion, EmotionState):
                    self._monitor.set_emotion_state(
                        emotion.valence,
                        emotion.arousal,
                        emotion.dominance,
                    )

        self._apply_talkative_overrides(event.plan)

        if self._should_skip_proactive(event.plan):
            logger.info(
                "ExecutionManager: suppressed proactive (talkative=%d), skipping LLM",
                event.plan.get("talkative_degree", 0),
            )
            return

        logger.info(
            "ExecutionManager: executing plan session=%s abbreviated=%s",
            event.plan.get("session_id"),
            event.plan.get("abbreviated"),
        )
        self._execute_general(event.plan)

    @staticmethod
    def _apply_talkative_overrides(plan: dict[str, Any]) -> None:
        """多弁度（talkative_degree）に応じてプランパラメータを上書き調整する。"""
        degree = plan.get("talkative_degree", 0)
        if degree <= 0:
            return
        if degree >= 1:
            plan["abbreviated"] = True
        if degree >= 2:
            current = plan.get("max_tokens", 0)
            if current > 0:
                plan["max_tokens"] = min(current, 256)
        if degree >= 3:
            plan["run_reflexion"] = False
            plan["run_compression"] = False
        if degree >= 5:
            plan["streaming"] = False
            plan["show_thinking"] = False

    def _should_skip_proactive(self, plan: dict[str, Any]) -> bool:
        content = plan.get("content", "")
        if content:
            return False
        if not self._monitor:
            return False
        talkative = plan.get("talkative_degree", 0) or self._monitor.talkative_degree
        return talkative >= 2 or (self._monitor.frequency_exceeded and talkative >= 1)

    def _execute_general(self, plan: dict[str, Any]) -> None:
        """プランに基づいてLLMの呼び出しと関連処理（ストリーミング、履歴保存、記憶連携など）を実行する。"""
        session_id = plan.get("session_id", "")
        content = plan.get("content", "")
        abbreviated = plan.get("abbreviated", False)
        streaming = plan.get("streaming", not abbreviated)
        show_thinking = plan.get("show_thinking", not abbreviated)
        run_reflexion = plan.get("run_reflexion", not abbreviated)
        run_compression = plan.get("run_compression", not abbreviated)
        record_history = plan.get("record_history", True)
        if content:
            plan["tools_allowed"] = True

        if record_history and content:
            self._messages.append({"role": "user", "content": content})
            self._last_activity_time = time.time()

        if content and self._memory:
            self._memory.short_term.add_turn("user", content)

        if show_thinking:
            self._event_bus.publish(
                MessageEvent(
                    timestamp=None,
                    source="execution",
                    msg_type="chat",
                    content="",
                    state=StreamState.THINKING.value,
                    direction="stream",
                )
            )

        if self._session_roles_getter and not abbreviated:
            self._pipeline.set_session_roles_summary(self._session_roles_getter())

        on_token: Callable[[str], None] | None = None
        if streaming:

            def _on_token(delta: str) -> None:
                self._event_bus.publish(
                    MessageEvent(
                        timestamp=None,
                        source="execution",
                        msg_type="chat",
                        content=delta,
                        state=StreamState.SPEAKING.value,
                        direction="stream",
                    )
                )

            on_token = _on_token

        try:
            if self._inhibition:
                self._inhibition.set_generating(True)
            response_text = self._pipeline.generate(
                plan=plan,
                messages=self._messages,
                on_token=on_token,
            )
        except Exception as e:
            response_text = f"[Error: {e}]"
            logger.exception("LLM call failed")
        finally:
            if self._inhibition:
                self._inhibition.set_generating(False)

        if record_history:
            self._messages.append({"role": "assistant", "content": response_text})
            self._last_activity_time = time.time()
            self._msg_count_since_reflect += 1

        if response_text and self._memory:
            self._memory.short_term.add_turn("assistant", response_text)

        logger.info(
            "ExecutionManager: response session=%s len=%d",
            session_id,
            len(response_text),
        )

        if show_thinking:
            self._event_bus.publish(
                MessageEvent(
                    timestamp=None,
                    source="execution",
                    msg_type="chat",
                    content="",
                    state=StreamState.DONE.value,
                    direction="stream",
                )
            )

        self._event_bus.publish(
            MessageEvent(
                timestamp=None,
                source="execution",
                msg_type="chat",
                content=response_text,
                direction="response",
            )
        )

        if self._monitor:
            flags = self._monitor.record_output()
            self._handle_monitor_flags(flags)

        def _post_process() -> None:
            try:
                if run_reflexion and self._hippocampal:
                    self._msg_count_since_reflect = self._hippocampal.maybe_run(
                        self._messages,
                        self._msg_count_since_reflect,
                    )
                if run_compression and self._context_window_mgr:
                    model_role = plan.get("model_role", "default")
                    effective_ctx = (
                        self._model_config.get_effective_context_window(model_role)
                        if self._model_config
                        else self._context_window
                    )
                    model_name = self._model_config.get_model(model_role) if self._model_config else None
                    summary = self._context_window_mgr.check_and_summarize(
                        self._messages,
                        effective_ctx,
                        model_name=model_name,
                    )
                    if summary and len(self._messages) > 6:
                        keep = 6
                        self._messages = [
                            {"role": "system", "content": f"## Session Summary\n{summary}"},
                            *self._messages[-keep:],
                        ]
                        logger.info("Auto-compacted: summary_len=%d, kept=%d", len(summary), keep)
            except Exception:
                logger.exception("Post-process failed")

        if run_reflexion or run_compression:
            threading.Thread(target=_post_process, daemon=True).start()

    def _handle_monitor_flags(self, flags: list[str]) -> None:
        """モニターからのフラグ（多弁など）を基に、ペナルティ適用などの抑制制御を行う。"""
        if not self._monitor:
            return

        if self._inhibition:
            self._inhibition.set_output_frequency_state(
                self._monitor.outputs_since_last_input,
                self._monitor.frequency_exceeded,
            )

        if "talkative" in flags and self._inhibition:
            degree = self._monitor.talkative_degree
            self._inhibition.apply_frequency_penalty(degree)
            logger.debug("Applied frequency penalty: degree=%d", degree)

        if flags:
            self._event_bus.publish(
                MonitorFeedback(
                    timestamp=None,
                    source="execution",
                    flags=flags,
                    content=",".join(flags),
                )
            )

    def flush_memory(self) -> None:
        """会話履歴から海馬反射（リフレクション）を強制実行し、記憶の永続化を行う。"""
        if self._hippocampal:
            self._hippocampal.force_run(self._messages)
        if self._memory:
            self._memory.flush()

    def compact_context(self) -> str:
        """手動で会話履歴のコンテキスト圧縮を実行する。"""
        if self._context_window_mgr is None:
            return "Context manager not available"
        if len(self._messages) < 2:
            return "Not enough messages to compact"
        summary = self._context_window_mgr.compact(self._messages)
        keep = 6
        self._messages = [{"role": "system", "content": f"## Session Summary\n{summary}"}, *self._messages[-keep:]]
        return f"Compacted: {len(summary)} chars summary, kept last {keep} messages"

    def _on_timer_tick(self, event: TimerTick) -> None:
        """タイマーイベントを受信したときの処理。待機時間リフレクションをチェックする。"""
        if self._msg_count_since_reflect <= 0:
            return
        if self._is_reflecting:
            return

        timeout = 180.0
        if self._config and hasattr(self._config, "proactive"):
            timeout = getattr(self._config.proactive, "idle_reflection_timeout_sec", 180.0)

        elapsed = time.time() - self._last_activity_time
        if elapsed >= timeout:
            logger.info(
                "ExecutionManager: idle reflection triggered. elapsed=%.1fs >= timeout=%.1fs, msg_count=%d",
                elapsed,
                timeout,
                self._msg_count_since_reflect,
            )
            self._run_idle_reflection()

    def _run_idle_reflection(self) -> None:
        """非同期でリフレクション（強制実行）を行う。"""
        with self._reflect_lock:
            if self._is_reflecting:
                return
            self._is_reflecting = True

        def _task() -> None:
            try:
                if self._hippocampal:
                    self._hippocampal.force_run(self._messages)
                    self._msg_count_since_reflect = 0
            except Exception:
                logger.exception("Idle reflection failed")
            finally:
                with self._reflect_lock:
                    self._is_reflecting = False

        threading.Thread(target=_task, daemon=True, name="idle-reflection").start()
