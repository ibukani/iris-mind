from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from loguru import logger

from iris.agency.internal_bus import PlanDecided
from iris.agency.planning.models import Plan
from iris.event.event_types import InterruptEvent

if TYPE_CHECKING:
    from iris.agency.internal_bus import InternalBus
    from iris.event.event_bus import EventBus


class _FlowControlProtocol(Protocol):
    def cancel_execution(self) -> None: ...
    def enqueue(self, item: Plan) -> None: ...


class _FlowExecutionHandler:
    def __init__(
        self,
        event_bus: EventBus,
        internal_bus: InternalBus,
        controller: _FlowControlProtocol,
    ) -> None:
        self._controller = controller
        event_bus.subscribe("InterruptEvent", self._on_interrupt)
        internal_bus.subscribe("PlanDecided", self._on_plan)

    def _on_interrupt(self, event: InterruptEvent) -> None:
        logger.info("FlowExecutionHandler: cancelling current execution due to interrupt")
        self._controller.cancel_execution()

    def _on_plan(self, event: PlanDecided) -> None:
        plan = event.plan
        logger.info(
            "FlowExecutionHandler: queueing plan session={}",
            plan.session_id,
        )
        self._controller.enqueue(plan)
