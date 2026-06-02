from typing import Protocol

from iris.contracts.actions import ActionPlan, PresentedOutput


class Presenter(Protocol):
    async def present(self, plan: ActionPlan) -> PresentedOutput: ...


class SimplePresenter:
    async def present(self, plan: ActionPlan) -> PresentedOutput:
        return PresentedOutput(
            text=plan.candidate_text,
            priority=plan.priority,
            interruptible=plan.interruptible,
        )
