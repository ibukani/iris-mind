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


def _run_in_background(target: Callable[[], None], *, name: str = "bg-task") -> None:
    threading.Thread(target=target, daemon=True, name=name).start()


class ExecutionManager:
    """意思決定されたプランに基づいてLLMの実行、出力監視、記憶の更新を統合管理するクラス。

    脳科学のアナロジー：
        - 運動野・基底核に対応し、行動（LLM Pipelineの実行、ツール実行）を担当。
    """

    TALKATIVE_ABBREVIATED_THRESHOLD = 1
    TALKATIVE_TOKEN_LIMIT_THRESHOLD = 2
    TALKATIVE_SKIP_POSTPROCESS_THRESHOLD = 3
    TALKATIVE_DISABLE_STREAM_THRESHOLD = 5

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

    def get_state(self) -> dict:
        return {
            "is_reflecting": self._is_reflecting,
            "msg_count": len(self._messages),
            "msg_count_since_reflect": self._msg_count_since_reflect,
            "idle_seconds": time.time() - self._last_activity_time if self._last_activity_time else 0,
            "talkative_degree": self._monitor.talkative_degree if self._monitor else 0,
        }

    def _on_plan(self, event: PlanDecided) -> None:
        plan = event.plan
        if self._monitor:
            if plan.get("content", ""):
                self._monitor.record_user_input()
            plan["talkative_degree"] = self._monitor.talkative_degree
            self._update_inhibition_state()
            self._apply_emotion_to_monitor(plan)

        self._apply_talkative_overrides(plan)

        if self._should_skip_proactive(plan):
            logger.info(
                "ExecutionManager: suppressed proactive (talkative=%d), skipping LLM",
                plan.get("talkative_degree", 0),
            )
            return

        logger.info(
            "ExecutionManager: executing plan session=%s abbreviated=%s",
            plan.get("session_id"),
            plan.get("abbreviated"),
        )
        self._execute_general(plan)

    def _update_inhibition_state(self) -> None:
        if self._monitor and self._inhibition:
            self._inhibition.set_output_frequency_state(
                self._monitor.outputs_since_last_input,
                self._monitor.frequency_exceeded,
            )

    def _apply_emotion_to_monitor(self, plan: dict[str, Any]) -> None:
        if not self._monitor:
            return
        emotion = plan.get("current_emotion")
        if not emotion:
            return
        from iris.limbic.models import EmotionState

        if isinstance(emotion, EmotionState):
            self._monitor.set_emotion_state(
                emotion.valence,
                emotion.arousal,
                emotion.dominance,
            )

    @classmethod
    def _apply_talkative_overrides(cls, plan: dict[str, Any]) -> None:
        degree = plan.get("talkative_degree", 0)
        if degree <= 0:
            return
        if degree >= cls.TALKATIVE_ABBREVIATED_THRESHOLD:
            plan["abbreviated"] = True
        if degree >= cls.TALKATIVE_TOKEN_LIMIT_THRESHOLD:
            current = plan.get("max_tokens", 0)
            if current > 0:
                plan["max_tokens"] = min(current, 256)
        if degree >= cls.TALKATIVE_SKIP_POSTPROCESS_THRESHOLD:
            plan["run_reflexion"] = False
            plan["run_compression"] = False
        if degree >= cls.TALKATIVE_DISABLE_STREAM_THRESHOLD:
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
        content = plan.get("content", "")
        abbreviated = plan.get("abbreviated", False)
        streaming = plan.get("streaming", not abbreviated)
        show_thinking = plan.get("show_thinking", not abbreviated)
        run_reflexion = plan.get("run_reflexion", not abbreviated)
        run_compression = plan.get("run_compression", not abbreviated)
        record_history = plan.get("record_history", True)
        if content:
            plan["tools_allowed"] = True

        self._prepare_execution_context(plan, content, show_thinking, record_history)
        on_token = self._create_stream_callback() if streaming else None
        response_text = self._run_llm_generation(plan, on_token)
        self._finalize_execution(plan, response_text, show_thinking, record_history)

        if run_reflexion or run_compression:
            self._trigger_post_processes(plan, run_reflexion, run_compression)

    def _prepare_execution_context(
        self, plan: dict[str, Any], content: str, show_thinking: bool, record_history: bool
    ) -> None:
        """実行前に履歴の記録、短期記憶への登録、および思考中イベントの送信を行う。"""
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

        if self._session_roles_getter and not plan.get("abbreviated", False):
            self._pipeline.set_session_roles_summary(self._session_roles_getter())

    def _create_stream_callback(self) -> Callable[[str], None]:
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

        return _on_token

    def _run_llm_generation(self, plan: dict[str, Any], on_token: Callable[[str], None] | None) -> str:
        """LLMの生成を実行し、生成結果のテキストを返す。"""
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
        return response_text

    def _finalize_execution(
        self, plan: dict[str, Any], response_text: str, show_thinking: bool, record_history: bool
    ) -> None:
        """実行後に履歴・短期記憶へ応答を追加し、DONEイベントを送信、モニターフラグを処理する。"""
        session_id = plan.get("session_id", "")
        if not response_text:
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
            return

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

    def _trigger_post_processes(self, plan: dict[str, Any], run_reflexion: bool, run_compression: bool) -> None:
        _run_in_background(
            lambda: self._run_post_process(plan, run_reflexion, run_compression),
            name="post-process",
        )

    def _run_post_process(self, plan: dict[str, Any], run_reflexion: bool, run_compression: bool) -> None:
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
        if self._msg_count_since_reflect <= 0 or self._is_reflecting:
            return

        timeout = 180.0
        if self._config and hasattr(self._config, "proactive"):
            timeout = getattr(self._config.proactive, "idle_reflection_timeout_sec", 180.0)

        elapsed = time.time() - self._last_activity_time
        if elapsed < timeout:
            return

        logger.info(
            "ExecutionManager: idle reflection triggered. elapsed=%.1fs >= timeout=%.1fs, msg_count=%d",
            elapsed,
            timeout,
            self._msg_count_since_reflect,
        )
        self._run_idle_reflection()

    def _run_idle_reflection(self) -> None:
        with self._reflect_lock:
            if self._is_reflecting:
                return
            self._is_reflecting = True

        _run_in_background(self._idle_reflection_task, name="idle-reflection")

    def _idle_reflection_task(self) -> None:
        try:
            if self._hippocampal:
                self._hippocampal.force_run(self._messages)
                self._msg_count_since_reflect = 0
        except Exception:
            logger.exception("Idle reflection failed")
        finally:
            with self._reflect_lock:
                self._is_reflecting = False
