"""The four versioned playbooks for the local synthetic exercise."""

from dataclasses import dataclass
from typing import Literal

from jt.common import PlaybookStep, SignalType

StepMode = Literal["ai_auto", "ai_draft_human_confirm", "human_only"]
CustomerEffect = Literal["spend_money", "change_itinerary"]


@dataclass(frozen=True)
class Step:
    step_id: str
    mode: StepMode
    effects: tuple[CustomerEffect, ...] = ()

    def to_case_step(self) -> PlaybookStep:
        return PlaybookStep(
            step_id=self.step_id,
            mode=self.mode,
            requires_customer_confirmation=bool(self.effects),
        )


@dataclass(frozen=True)
class Playbook:
    playbook_id: str
    version: str
    steps: tuple[Step, ...]


P0_ASSISTANCE = Playbook(
    "p0_assistance", "1",
    (
        Step("prepare_emergency_guidance", "ai_auto"),
        Step("verify_assistance", "human_only"),
        Step("draft_assistance_summary", "ai_draft_human_confirm"),
    ),
)
DOCUMENT_LOSS = Playbook(
    "document_loss", "1",
    (
        Step("prepare_replacement_checklist", "ai_auto"),
        Step("verify_document_situation", "human_only"),
        Step("draft_document_guidance", "ai_draft_human_confirm"),
    ),
)
FLIGHT_CHANGE = Playbook(
    "flight_change", "1",
    (
        Step("summarize_flight_change", "ai_auto"),
        Step("draft_itinerary_change", "ai_draft_human_confirm", ("change_itinerary",)),
        Step("simulate_paid_rebooking", "human_only", ("spend_money",)),
    ),
)
AI_FAILURE = Playbook(
    "ai_failure", "1",
    (
        Step("summarize_repeated_failure", "ai_auto"),
        Step("verify_unresolved_request", "human_only"),
        Step("draft_recovery_summary", "ai_draft_human_confirm"),
    ),
)

PLAYBOOKS_BY_SIGNAL: dict[SignalType, Playbook] = {
    "safety": P0_ASSISTANCE,
    "illness": P0_ASSISTANCE,
    "document_loss": DOCUMENT_LOSS,
    "itinerary_disruption": FLIGHT_CHANGE,
    "ai_failure_loop": AI_FAILURE,
}
