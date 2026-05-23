from __future__ import annotations

from typing import TYPE_CHECKING, Any

from iris.event.event_types import MonitorFeedback

if TYPE_CHECKING:
    from iris.agency.execution.regulation.output_tracker import OutputTracker
    from iris.agency.inhibition import InhibitionController
    from iris.event.event_bus import EventBus
    from iris.limbic.models import EmotionState

from loguru import logger


class FeedbackCoordinator:
    """OutputTracker と InhibitionController 間の状態同期を担当。"""

    def __init__(
        self,
        event_bus: EventBus,
        monitor: OutputTracker | None = None,
        inhibition: InhibitionController | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._monitor = monitor
        self._inhibition = inhibition

    def sync_inhibition_state(self) -> None:
        if self._monitor and self._inhibition:
            self._inhibition.set_output_frequency_state(
                self._monitor.outputs_since_last_input,
                self._monitor.frequency_exceeded,
            )

    def apply_emotion_to_monitor(self, plan: dict[str, Any]) -> None:
        if not self._monitor:
            return
        emotion: EmotionState | None = plan.get("current_emotion")
        if emotion is None:
            return
        self._monitor.set_emotion_state(
            emotion.valence,
            emotion.arousal,
            emotion.dominance,
        )

    def process_feedback(self, flags: list[str]) -> None:
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
            logger.debug("Applied frequency penalty: degree={}", degree)

        if flags:
            self._event_bus.publish(
                MonitorFeedback(
                    timestamp=None,
                    source="execution",
                    flags=flags,
                    content=",".join(flags),
                )
            )
