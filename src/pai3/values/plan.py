"""One line of a treatment plan.

Embedded rather than normalised: a plan item has no lifecycle of its own and is
revised as part of the plan (§5). It may still point at a Condition or Medication.
"""

from pydantic import BaseModel, Field


class PlanItem(BaseModel):
    description: str = Field(min_length=1)
    targets: list[str] = Field(
        default_factory=list, description="Canonical ids this item acts on"
    )
    due: str | None = None
