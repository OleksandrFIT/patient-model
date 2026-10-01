"""The three tiers every canonical entity inherits from (§2).

Which class an entity extends is a statement about the data: CanonicalRecord for
practice-level and infrastructure records, PatientScoped for anything belonging to one
patient, ClinicalRecord for anything that may belong to an encounter.
"""

from pydantic import AwareDatetime, BaseModel, Field

from pai3.enums import RecordStatus
from pai3.values.actor import Actor
from pai3.values.provenance import Provenance


class CanonicalRecord(BaseModel):
    """Applies to Patient, Provider, AuditEvent, DataQualityFlag.

    Timestamps are `AwareDatetime`, which refuses a naive value outright: a clinical
    timestamp with no zone cannot be ordered across sites. No separate validator guards
    this — one that ran after AwareDatetime could never fire, and a validator that cannot
    fire is read later as the place the constraint lives.
    """

    id: str
    provenance: Provenance
    field_provenance: dict[str, Provenance] = Field(
        default_factory=dict,
        description="Per-entity whitelist only; see each entity's FIELD_PROVENANCE_WHITELIST",
    )
    record_status: RecordStatus = RecordStatus.ACTIVE
    version: int = Field(default=1, ge=1)
    superseded_by: str | None = None
    created_at: AwareDatetime
    updated_at: AwareDatetime
    updated_by: Actor

    @property
    def is_retracted(self) -> bool:
        """Retraction cascades to derivatives — see lineage.retraction_cascade (§6.19)."""
        return self.record_status is RecordStatus.ENTERED_IN_ERROR


class PatientScoped(CanonicalRecord):
    """Applies to Encounter, Consent, Coverage, Goal, SourceReference."""

    patient_id: str


class ClinicalRecord(PatientScoped):
    """Applies to the twelve entities that may belong to an encounter (§2.3)."""

    encounter_id: str | None = None
