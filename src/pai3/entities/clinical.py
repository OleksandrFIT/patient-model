"""Coded clinical statements, and the small entities that sit beside them.

Encounter, Procedure, Goal and SocialFactor arrive in Phases 2 and 3; this file holds
them all because they change together as the coding approach changes.
"""

from datetime import date
from enum import StrEnum
from typing import ClassVar

from pydantic import AwareDatetime, BaseModel, Field, model_validator

from pai3.base import ClinicalRecord, PatientScoped
from pai3.enums import ClinicalStatus, VerificationStatus
from pai3.values.codeable import CodeableConcept
from pai3.values.text import ClinicalText

_NOT_ASSERTABLE = {
    VerificationStatus.REFUTED,
    VerificationStatus.PROVISIONAL,
    VerificationStatus.DIFFERENTIAL,
    VerificationStatus.UNCONFIRMED,
}


class Condition(ClinicalRecord):
    """Medical history and current diagnoses in one entity (§6.4)."""

    FIELD_PROVENANCE_WHITELIST: ClassVar[frozenset[str]] = frozenset({"clinical_status"})

    code: CodeableConcept
    clinical_status: ClinicalStatus
    verification_status: VerificationStatus
    onset: date | None = None
    abatement: date | None = None
    recorded_by: str | None = Field(default=None, description="Provider id")

    @model_validator(mode="after")
    def _abatement_follows_onset(self) -> "Condition":
        if self.onset and self.abatement and self.abatement < self.onset:
            raise ValueError("abatement precedes onset")
        return self

    @property
    def is_assertable(self) -> bool:
        """Whether a summary may state this as fact.

        Only a confirmed condition qualifies. Everything else is a hypothesis, and
        §6.4 exists so that a hypothesis cannot be rendered as a diagnosis.
        """
        return self.verification_status not in _NOT_ASSERTABLE


class Criticality(StrEnum):
    """Potential for a life-threatening reaction — not the severity of a past one."""

    LOW = "low"
    HIGH = "high"
    UNABLE_TO_ASSESS = "unable_to_assess"


class Reaction(BaseModel):
    manifestation: CodeableConcept
    severity: str | None = None
    occurred: date | None = None


class AllergyIntolerance(ClinicalRecord):
    """Never embedded on Patient.

    The most safety-critical list in the model needs its own audit trail, and §10.6
    makes it non-droppable from any projection regardless of verification status.
    """

    substance: CodeableConcept
    criticality: Criticality
    verification_status: VerificationStatus
    reactions: list[Reaction] = Field(default_factory=list)
    recorded_by: str | None = None

    @property
    def is_assertable(self) -> bool:
        return self.verification_status not in _NOT_ASSERTABLE


class Encounter(PatientScoped):
    """A visit or contact — the grouping anchor for the pre-visit brief (§4).

    PatientScoped rather than ClinicalRecord: it is the encounter (§2.4).
    """

    encounter_type: str
    started_at: AwareDatetime
    ended_at: AwareDatetime | None = None
    participant_ids: list[str] = Field(default_factory=list)
    reason: CodeableConcept | None = None

    @model_validator(mode="after")
    def _period_is_ordered(self) -> "Encounter":
        if self.ended_at is not None and self.ended_at < self.started_at:
            raise ValueError("ended_at precedes started_at")
        return self


class Procedure(ClinicalRecord):
    """Thin (§4)."""

    code: CodeableConcept
    performed_on: date
    performer_id: str | None = None
    outcome: str | None = None


class Goal(PatientScoped):
    """Patient-owned, and outlives any single treatment plan (§2.4).

    PatientScoped rather than ClinicalRecord: a goal can exist before any plan and
    before any visit, which is why it did not fold into TreatmentPlan.
    """

    description: str = Field(min_length=1)
    target_date: date | None = None
    status: str = "active"


class SocialFactor(ClinicalRecord):
    """Smoking, alcohol, sleep, occupation, living situation.

    A record with an assertion date rather than a mutable block on Patient, because the
    whole risk here is staleness -- "smoker" recorded in 2019 and never revisited -- and
    a block has no history (§6.16).
    """

    factor: CodeableConcept
    value: str
    asserted_on: date


class SymptomStatus(StrEnum):
    ACTIVE = "active"
    RESOLVED = "resolved"


class SymptomReporter(StrEnum):
    """Who said so. The same trust axis §6.7 used to split Medication from Supplement."""

    PATIENT = "patient"
    CLINICIAN_OBSERVED = "clinician_observed"


class SymptomSeverity(StrEnum):
    MILD = "mild"
    MODERATE = "moderate"
    SEVERE = "severe"
    UNSPECIFIED = "unspecified"
    """An unrecorded severity is not a mild one."""


class Symptom(ClinicalRecord):
    """What the patient reports experiencing, and why it worries them (§6.20).

    Separate from Condition, and the reason is the one §6.4 is built on. A `Condition` carries
    `verification_status` because a diagnosis can be wrong; a symptom has none, because its
    existence is not in doubt — the patient reports fatigue, and whether that means
    hypothyroidism is the Condition's question, not this one. Folding symptoms into Condition
    as `unconfirmed` would make them read as weak diagnoses, and a brief could no longer tell
    "reports fatigue" from "has hypothyroidism".

    The clinical workflow runs symptom → differential → diagnosis, and the model has to be
    able to hold the left-hand side before the right-hand side exists.
    """

    FIELD_PROVENANCE_WHITELIST: ClassVar[frozenset[str]] = frozenset({"status", "severity"})

    symptom: CodeableConcept
    status: SymptomStatus
    reported_by: SymptomReporter
    severity: SymptomSeverity = SymptomSeverity.UNSPECIFIED
    onset: date | None = None
    resolved_on: date | None = None
    patient_concern: ClinicalText | None = Field(
        default=None,
        description="Why it worries the patient, in their words. Carries PATIENT_SUBMITTED",
    )

    @model_validator(mode="after")
    def _resolution_follows_onset(self) -> "Symptom":
        # No date is demanded for a resolved symptom, unlike a stopped Medication (§9.8).
        # A patient who says the headache stopped rarely knows when, and demanding the date
        # would discard the fact that it stopped.
        if self.onset and self.resolved_on and self.resolved_on < self.onset:
            raise ValueError("resolved_on precedes onset")
        return self

    @model_validator(mode="after")
    def _a_concern_came_from_outside(self) -> "Symptom":
        """A concern in the patient's own words cannot be practice-authored (§10.1)."""
        if self.patient_concern is not None and not self.patient_concern.crossed_perimeter:
            raise ValueError(
                "patient_concern must carry an origin that crossed the perimeter; "
                f"got {self.patient_concern.origin.value}"
            )
        return self

    @property
    def is_current(self) -> bool:
        return self.status is SymptomStatus.ACTIVE
