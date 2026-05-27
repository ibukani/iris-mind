from __future__ import annotations

from typing import TYPE_CHECKING, Any

from iris.agency.planning.models import Plan, PlanReason

if TYPE_CHECKING:
    from iris.agency.planning.question_generator import QuestionGenerator


class ProactivePlanStrategy:
    def __init__(
        self,
        question_gen: QuestionGenerator | None = None,
    ) -> None:
        self._question_gen = question_gen

    def build_proactive(
        self,
        context: dict[str, Any],
    ) -> Plan:
        context_hint: str = context.get("context_hint", "")
        overrides: dict[str, Any] = {}

        if context.get("is_silent_proactive", False):
            topic = context.get("topic", "general")
            overrides["proactive_reason"] = topic

            plan = Plan(
                content="",
                task_level="normal",
                silent=True,
                reason=PlanReason.PROACTIVE_CURIOSITY,
                context_hint=context_hint,
                overrides=overrides,
            )
        elif context.get("escalation"):
            topic = context.get("topic", "") or ""
            summary = context.get("summary", "")
            if topic and summary:
                content = f"あなたは『{topic}』について調査し、次のことが分かりました：『{summary}』"
            elif topic:
                content = f"あなたは『{topic}』について調査しました。"
            elif summary:
                content = f"あなたは調査により次のことを発見しました：『{summary}』"
            else:
                content = ""
            if not content:
                plan = Plan(
                    content="",
                    task_level="normal",
                    silent=True,
                    reason=PlanReason.PROACTIVE_CURIOSITY,
                    context_hint=context_hint,
                    overrides=overrides,
                )
            else:
                plan = Plan(
                    content=content,
                    task_level="deep",
                    silent=False,
                    reason=PlanReason.PROACTIVE_ESCALATION,
                    context_hint=context_hint,
                    overrides=overrides,
                )
        else:
            plan = Plan(
                content="",
                task_level="light",
                silent=True,
                reason=PlanReason.TIMER_EVENT,
                context_hint=context_hint,
                overrides=overrides,
            )

        return plan
