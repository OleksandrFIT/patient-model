"""SourceReference, DataQualityFlag, AuditEvent.

The flag and the event are practice-level: they must be able to target a Provider,
which has no patient, so they inherit CanonicalRecord and carry `patient_id` only as a
denormalised key for the per-patient review queue and audit export (§2.4).
"""

from enum import StrEnum

from pydantic import AwareDatetime, BaseModel, Field, model_validator

from pai3.base import CanonicalRecord, PatientScoped
from pai3.enums import FlagCode, FlagStatus, Severity
from pai3.ids import CanonicalRef
from pai3.values.actor import Actor


class SourceReference(PatientScoped):
    """A pointer into a source document — the single citation primitive (§6.17).

    Normalised rather than embedded because one lab PDF supports forty lab results;
    embedding would kill "show me everything from this report" and multiply storage.
    """

    document_id: str = Field(min_length=1)
    page: int | None = Field(default=None, ge=1)
    field_path: str | None = None
    span_start: int | None = Field(default=None, ge=0)
    span_end: int | None = Field(default=None, ge=0)
    quote: str | None = None


class FlagTarget(BaseModel):
    entity_type: str
    entity_id: str
    field_path: str | None = None


class DataQualityFlag(CanonicalRecord):
    """A defect, with its own lifecycle (§6.5).

    An entity rather than an embedded list, for three reasons: the review queue is a
    cross-patient query; a conflict exists between two records and needs two targets;
    and its lifecycle is independent of the clinical record's version, so embedding
    would bury change history under review noise.
    """

    patient_id: str | None = Field(
        default=None, description="Denormalised query key, not ownership"
    )
    code: FlagCode
    severity: Severity
    message: str = Field(min_length=1)
    status: FlagStatus = FlagStatus.OPEN
    targets: list[FlagTarget] = Field(default_factory=list)
    candidates: list[str] = Field(
        default_factory=list,
        description="SourceReference ids for the competing values in a conflict",
    )
    source_locator: list[str] = Field(
        default_factory=list,
        description="SourceReference ids, when no canonical record exists to target (§9.7)",
    )

    @model_validator(mode="after")
    def _points_at_something(self) -> "DataQualityFlag":
        if not self.targets and not self.source_locator:
            raise ValueError("a flag needs targets or a source_locator to be actionable")
        return self

    @property
    def blocks_autonomous_use(self) -> bool:
        """§9.1: blocking blocks autonomous conclusion, never persistence."""
        return self.severity is Severity.BLOCKING and self.status in (
            FlagStatus.OPEN,
            FlagStatus.IN_REVIEW,
        )


class AuditAction(StrEnum):
    READ = "read"
    CREATE = "create"
    UPDATE = "update"
    RETRACT = "retract"
    INGEST_STARTED = "ingest_started"
    INGEST_COMPLETED = "ingest_completed"
    INGEST_FAILED = "ingest_failed"


_INGEST_ACTIONS = {
    AuditAction.INGEST_STARTED,
    AuditAction.INGEST_COMPLETED,
    AuditAction.INGEST_FAILED,
}


class IngestSummary(BaseModel):
    """Counts for one ingestion attempt (§9.7).

    `expected` is None when the document declares no count — a free-form PDF. That is
    not flagged, because one flag per PDF is noise, but it stays here so that "which
    documents have unverifiable completeness" remains an ordinary query. Not flagging
    something and not knowing it are different claims, and None is the second.
    """

    source_document_id: str
    expected: int | None = Field(default=None, ge=0)
    accepted: int = Field(default=0, ge=0)
    rejected: int = Field(default=0, ge=0)
    failure_reason: str | None = None

    @property
    def completeness_verifiable(self) -> bool:
        return self.expected is not None

    @property
    def unaccounted(self) -> int | None:
        """Rows the document claimed that neither landed nor were rejected."""
        if self.expected is None:
            return None
        return self.expected - self.accepted - self.rejected


class AuditEvent(CanonicalRecord):
    """Append-only. Logs reads as well as writes (§6.3).

    Payloads are populated by action: `fields_read` on reads, `ingest` on ingestion,
    `field_delta` on writes. That is the ordinary shape of an event log — each field is
    documented by the action that fills it and absent otherwise.
    """

    patient_id: str | None = Field(default=None, description="Denormalised query key")
    action: AuditAction
    trace_id: str = Field(
        min_length=1,
        description=(
            "The unit of work: one brief generation, one extraction run, one agent turn"
        ),
    )
    actor: Actor | None = None
    targets: list[str] = Field(
        default_factory=list,
        description="Reads batch by (trace_id, entity_type); writes keep a single target",
    )
    fields_read: list[str] | None = Field(
        default=None,
        description="None means unknown — assume the whole record was read (§6.3)",
    )
    field_delta: dict[str, tuple[str | None, str | None]] = Field(default_factory=dict)
    ingest: IngestSummary | None = None
    occurred_at: AwareDatetime | None = None
    inputs: list[CanonicalRef] = Field(default_factory=list)

    @model_validator(mode="after")
    def _ingest_payload_matches_the_action(self) -> "AuditEvent":
        is_ingest = self.action in _INGEST_ACTIONS
        if self.ingest is not None and not is_ingest:
            raise ValueError(
                f"ingest payload is only valid on ingest actions, not {self.action}"
            )
        if self.ingest is None and is_ingest:
            raise ValueError(f"{self.action} requires an ingest payload")
        return self
