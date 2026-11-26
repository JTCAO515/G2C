"""Versioned playbook progress around the frozen Case record."""

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from .models import Case, PlaybookStep, _ContractModel

NonNegativeInteger = Annotated[int, Field(strict=True, ge=0)]


class CaseExecution(_ContractModel):
    schema_version: Literal["jt-case-execution.v1"]
    case: Case
    revision: NonNegativeInteger
    step_index: NonNegativeInteger
    draft: str | None
    customer_consent_recorded: bool = Field(strict=True)

    @property
    def active_step(self) -> PlaybookStep | None:
        if self.step_index == len(self.case.steps):
            return None
        return self.case.steps[self.step_index]

    @model_validator(mode="after")
    def check_progress(self) -> Self:
        if self.step_index > len(self.case.steps):
            raise ValueError("current step is outside the playbook")
        step = self.active_step
        if (step is None) != (self.case.status == "closed"):
            raise ValueError("only a completed playbook has a closed case")
        if self.case.status == "open" and (
            self.step_index != 0 or self.draft is not None or self.customer_consent_recorded
        ):
            raise ValueError("an open case has not started its playbook")
        if self.draft is not None and (step is None or step.mode != "ai_draft_human_confirm"):
            raise ValueError("only an active draft step can hold a draft")
        if self.customer_consent_recorded and (
            step is None or not step.requires_customer_confirmation
            or (step.mode == "ai_draft_human_confirm" and self.draft is None)
        ):
            raise ValueError("customer consent must be bound to an active applicable step")
        return self
