"""Task-understanding model output (W2-8, #1738): data only, never a write or tool grant.

One message can carry several tasks (for example a trade-fair visit plus a
sightseeing question). The model lists them with the scene pack each belongs
to, an optional flow id from that pack and the facts still missing; the host
validates every task against the traveler's own words and the active packs,
then picks at most one question in code.
"""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

TASKS = 'LIO-tasks.1'
MISSING_FIELDS = ('city', 'dates', 'days', 'party', 'venue', 'hotel', 'budget', 'nationality')


class DTO(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid', frozen=True)


class TaskSource(DTO):
    source_index: int = Field(ge=0)
    quote: str = Field(min_length=1, max_length=600)


class Task(DTO):
    pack: Literal['travel', 'business']
    topic: str = Field(min_length=1, max_length=80)
    flow: str | None = Field(max_length=80)
    missing: list[Literal[MISSING_FIELDS]] = Field(max_length=4)
    source: TaskSource


class TaskPlan(DTO):
    version: Literal['LIO-tasks.1']
    current_source_index: int = Field(ge=0)
    tasks: list[Task] = Field(max_length=4)
