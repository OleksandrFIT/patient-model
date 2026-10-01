"""Task — follow-ups and workflow state.

An AI-extracted task lands PROPOSED and is never opened and assigned by the pipeline.
Assignment is the human approval step in §10.4's rights matrix.
"""

from datetime import date
from enum import StrEnum

from pydantic import Field, model_validator

from pai3.base import ClinicalRecord


class TaskStatus(StrEnum):
    PROPOSED = "proposed"
    OPEN = "open"
    DONE = "done"
    CANCELLED = "cancelled"


class TaskOrigin(StrEnum):
    HUMAN = "human"
    AI_SUGGESTED = "ai_suggested"


class Task(ClinicalRecord):
    description: str = Field(min_length=1)
    origin: TaskOrigin
    status: TaskStatus = TaskStatus.PROPOSED
    assignee_id: str | None = None
    due_on: date | None = None
    source_ref: str | None = Field(
        default=None, description="The note or lab this follow-up came from"
    )

    @model_validator(mode="after")
    def _ai_tasks_are_not_self_assigning(self) -> "Task":
        if self.origin is TaskOrigin.AI_SUGGESTED and self.status is not TaskStatus.PROPOSED:
            raise ValueError(
                "an ai_suggested task must stay proposed until a human assigns it"
            )
        return self
