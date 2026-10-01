"""Medication, Supplement and TreatmentPlan.

Medication and Supplement are separate entities on an axis of trust rather than field
overlap (§6.7): a drug was asserted by a prescriber, a supplement is self-reported, has
no reliable numeric dose, usually has no RxNorm code, and is checked for interactions
against a different knowledge base. Supplement and TreatmentPlan arrive in Phase 2.
"""

from datetime import date
from enum import StrEnum
from typing import ClassVar

from pydantic import Field, model_validator

from pai3.base import ClinicalRecord
from pai3.values.codeable import CodeableConcept
from pai3.values.dosage import Dosage
from pai3.values.plan import PlanItem


class MedicationStatus(StrEnum):
    ACTIVE = "active"
    HELD = "held"
    STOPPED = "stopped"
    COMPLETED = "completed"


class Medication(ClinicalRecord):
    FIELD_PROVENANCE_WHITELIST: ClassVar[frozenset[str]] = frozenset({"dose", "status"})

    drug: CodeableConcept
    dosage: Dosage
    status: MedicationStatus
    started_on: date | None = None
    stopped_on: date | None = None
    prescriber_id: str | None = Field(default=None, description="Provider id")
    indication: str | None = None

    @model_validator(mode="after")
    def _stop_date_agrees_with_status(self) -> "Medication":
        ended = self.status in (MedicationStatus.STOPPED, MedicationStatus.COMPLETED)
        if ended and self.stopped_on is None:
            raise ValueError(f"status {self.status} requires stopped_on")
        if not ended and self.stopped_on is not None:
            raise ValueError(
                f"stopped_on is set but status is {self.status}; "
                "a discontinued medication must not present as active"
            )
        if self.started_on and self.stopped_on and self.stopped_on < self.started_on:
            raise ValueError("stopped_on precedes started_on")
        return self

    @property
    def is_current(self) -> bool:
        """§10.6 makes a current medication non-droppable from any projection."""
        return self.status in (MedicationStatus.ACTIVE, MedicationStatus.HELD)


class SupplementStatus(StrEnum):
    ACTIVE = "active"
    STOPPED = "stopped"


class Supplement(ClinicalRecord):
    """Almost always patient-reported (§6.7).

    No prescriber, no reliable numeric dose, usually no RxNorm code. Interaction
    checking against supplements uses a different knowledge base, so every consumer
    would branch on a `kind` discriminator anyway if this were merged with Medication.

    Unlike Medication there is no rule tying `status` to `stopped_on`, and that is the
    trust axis showing through rather than an omission: a patient who says they stopped
    the vitamin D rarely knows when, and demanding the date would throw away the fact
    that they stopped. Medication can demand it because a prescriber recorded the change.
    """

    FIELD_PROVENANCE_WHITELIST: ClassVar[frozenset[str]] = frozenset({"dose", "status"})

    substance: CodeableConcept
    dosage: Dosage
    status: SupplementStatus
    started_on: date | None = None
    stopped_on: date | None = None
    reported_reason: str | None = None

    @property
    def is_current(self) -> bool:
        return self.status is SupplementStatus.ACTIVE


class TreatmentPlan(ClinicalRecord):
    """Items are embedded: no independent lifecycle, revised with the plan (§5)."""

    title: str = Field(min_length=1)
    items: list[PlanItem] = Field(min_length=1)
    authored_by: str | None = Field(default=None, description="Provider id")
