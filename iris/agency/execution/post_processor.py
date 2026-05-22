from __future__ import annotations

from collections.abc import Callable
import logging
import threading
import time
from typing import TYPE_CHECKING, Any

from iris.agency.inhibition import InhibitionController
from iris.event.event_bus import EventBus
from iris.event.event_types import ProactiveResultEvent, TimerTick

if TYPE_CHECKING:
    from iris.kernel.config import Config, ModelConfig
    from iris.llm.context_window import LLMContextWindowManager
    from iris.memory.hippocampal.manager import HippocampalManager

logger = logging.getLogger(__name__)


def _run_in_background(target: Callable[[], None], *, name: str = "bg-task") -> None:
    threading.Thread(target=target, daemon=True, name=name).start()


class PostProcessor:
    def __init__(
        self,
        event_bus: EventBus,
        messages_getter: Callable[[], list[dict[str, Any]]],
        hippocampal: HippocampalManager | None = None,
        context_window_mgr: LLMContextWindowManager | None = None,
        model_config: ModelConfig | None = None,
        context_window: int = 0,
        inhibition: InhibitionController | None = None,
        config: Config | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._get_messages = messages_getter
        self._hippocampal = hippocampal
        self._context_window_mgr = context_window_mgr
        self._model_config = model_config
        self._context_window = context_window
        self._inhibition = inhibition
        self._config = config
        self._last_activity_time = time.time()
        self._msg_count_since_reflect = 0
        self._reflect_lock = threading.Lock()
        self._is_reflecting = False
        event_bus.subscribe("TimerTick", self._on_timer_tick)
        event_bus.subscribe("ProactiveResultEvent", self._on_proactive_result)

    def record_activity(self) -> None:
        self._last_activity_time = time.time()

    def increment_reflect_count(self) -> None:
        self._msg_count_since_reflect += 1

    def trigger_post_processes(self, plan: dict[str, Any], run_reflexion: bool, run_compression: bool) -> None:
        _run_in_background(
            lambda: self._run_post_process(plan, run_reflexion, run_compression),
            name="post-process",
        )

    def _run_post_process(self, plan: dict[str, Any], run_reflexion: bool, run_compression: bool) -> None:
        messages = self._get_messages()
        try:
            if run_reflexion and self._hippocampal:
                self._msg_count_since_reflect = self._hippocampal.maybe_run(
                    messages,
                    self._msg_count_since_reflect,
                )
            if run_compression and self._context_window_mgr:
                self._compact_messages(messages, plan)
        except Exception:
            logger.exception("Post-process failed")

    def _compact_messages(self, messages: list[dict[str, Any]], plan: dict[str, Any]) -> None:
        cwm = self._context_window_mgr
        if cwm is None:
            return
        model_role = plan.get("model_role", "default")
        effective_ctx = (
            self._model_config.get_effective_context_window(model_role) if self._model_config else self._context_window
        )
        model_name = self._model_config.get_model(model_role) if self._model_config else None
        summary = cwm.check_and_summarize(
            messages,
            effective_ctx,
            model_name=model_name,
        )
        if not summary or len(messages) <= 6:
            return
        keep = 6
        messages[:] = [
            {"role": "system", "content": f"## Session Summary\n{summary}"},
            *messages[-keep:],
        ]
        logger.info("Auto-compacted: summary_len=%d, kept=%d", len(summary), keep)

    def flush_memory(self) -> None:
        if self._hippocampal:
            self._hippocampal.force_run(self._get_messages())

    def compact_context(self) -> str:
        if self._context_window_mgr is None:
            return "Context manager not available"
        messages = self._get_messages()
        if len(messages) < 2:
            return "Not enough messages to compact"
        summary = self._context_window_mgr.compact(messages)
        keep = 6
        messages[:] = [{"role": "system", "content": f"## Session Summary\n{summary}"}, *messages[-keep:]]
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
            "PostProcessor: idle reflection triggered. elapsed=%.1fs >= timeout=%.1fs, msg_count=%d",
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
                self._hippocampal.force_run(self._get_messages())
                self._msg_count_since_reflect = 0
        except Exception:
            logger.exception("Idle reflection failed")
        finally:
            with self._reflect_lock:
                self._is_reflecting = False

    def get_state(self) -> dict:
        return {
            "is_reflecting": self._is_reflecting,
            "msg_count_since_reflect": self._msg_count_since_reflect,
            "idle_seconds": time.time() - self._last_activity_time if self._last_activity_time else 0,
        }

    def _on_proactive_result(self, event: ProactiveResultEvent) -> None:
        hippocampal = self._hippocampal
        if hippocampal is None:
            return
        _run_in_background(
            lambda: hippocampal.process_proactive_result(
                topic=event.topic,
                success=event.success,
                content=event.content,
            ),
            name="proactive-result-process",
        )
