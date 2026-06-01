from __future__ import annotations

from typing import Any

from iris.event.base import TimerTick
from iris.memory.events import ProactiveTrigger
from iris.memory.sensory.handler import SensoryEventHandler


class _MemoryEventHandler:
    """Memory 層のイベントハンドラ。

    責務:
    - EventBus 上のイベントを購読し、記憶系の処理を行う
    - 通常メッセージ: Gateway → EventBus.publish(InputReady) → subscribe で受信
    - Room 参加/退室: Sensory / ShortTerm 各個別ハンドラに委譲
    - TimerTick/プロアクティブ: ProactiveTrigger に委譲

    設計:
    - control メッセージは KernelManager で room.* と account.* に分岐し、
      Memory 層には届かない。Memory 層は Room イベント経由で間接的に処理する。
    - InhibitionRequestEvent は InhibitionEventHandler が処理し、Memory 層には届かない。
    """

    def __init__(
        self,
        event_bus: Any,
        sensory_handler: SensoryEventHandler,
        proactive_trigger: ProactiveTrigger,
        proactive_config: Any,
    ) -> None:

        self.event_bus = event_bus
        self._sensory_handler = sensory_handler
        self._proactive_trigger = proactive_trigger
        self.proactive_config = proactive_config

        # イベント購読の登録
        event_bus.subscribe(TimerTick, self._on_timer_tick)

    def _on_timer_tick(self, event: TimerTick) -> None:
        if self.event_bus is None:
            return
        # 感覚記憶のイベント処理を委譲。何か入力を処理した場合はプロアクティブ処理を行わない
        if self._sensory_handler._on_timer_tick(event):
            return

        if self.proactive_config is not None:
            self._proactive_trigger.publish()
