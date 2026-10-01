"""Closed enumerations.

Each of these is closed rather than a free string because consumers branch on the
value (spec §6.5). A value that can be anything makes every branch unsound, and in
the case of `execution` in §10.2 it makes an invariant unenforceable.
"""

from enum import StrEnum


class RecordStatus(StrEnum):
    """There is deliberately no `deleted`.

    An erroneous record stays as ENTERED_IN_ERROR, because deleting it removes the
    reason a physician prescribed something while the prescription remains (§2.1).
    """

    ACTIVE = "active"
    SUPERSEDED = "superseded"
    ENTERED_IN_ERROR = "entered_in_error"


class ProvenanceOrigin(StrEnum):
    """Where a value came from, one meaning per member (§6.19).

    AI_EXTRACTION and AI_INFERENCE are separate because the second compounds: a fact
    inferred from other facts can grow derivatives, and a single catch-all `derived`
    could not distinguish that from pipeline bookkeeping.
    """

    HUMAN = "human"
    SOURCE_SYSTEM = "source_system"
    AI_EXTRACTION = "ai_extraction"
    AI_INFERENCE = "ai_inference"
    SYSTEM_DERIVED = "system_derived"


class TextOrigin(StrEnum):
    """Whether a span of text crossed the practice perimeter (§10.1).

    The axis is not authorship. A physician who pastes a patient's message carries
    external text inside, and their signature does not change what the text is.
    UNKNOWN is treated as external everywhere: an unestablished origin is not a
    reason to trust.
    """

    PRACTICE_AUTHORED = "practice_authored"
    PATIENT_SUBMITTED = "patient_submitted"
    EXTERNAL_DOCUMENT = "external_document"
    TRANSCRIBED_EXTERNAL = "transcribed_external"
    UNKNOWN = "unknown"


class Severity(StrEnum):
    """D5's four classes (§9.1).

    BLOCKING does not block persistence. It blocks autonomous conclusion: the record
    exists and is citable, but no read-model or agent may assert from it without
    surfacing the flag.
    """

    BLOCKING = "blocking"
    HUMAN_REVIEW_REQUIRED = "human_review_required"
    WARNING = "warning"
    ACCEPTABLE_MISSING = "acceptable_missing"


class FlagCode(StrEnum):
    """Why a flag was raised (§6.5).

    Closed because under §6.9 and §9.3 this is the only carrier of *why* a value is
    absent — three different situations all present as an empty slot.
    """

    CONFLICTING_VALUES = "CONFLICTING_VALUES"
    MISSING_UNIT = "MISSING_UNIT"
    MISSING_REFERENCE_RANGE = "MISSING_REFERENCE_RANGE"
    UNIT_MISMATCH = "UNIT_MISMATCH"
    INTERPRETATION_DISAGREES_WITH_RANGE = "INTERPRETATION_DISAGREES_WITH_RANGE"
    EXTRACTION_FAILED = "EXTRACTION_FAILED"
    DISCONTINUED_SHOWN_ACTIVE = "DISCONTINUED_SHOWN_ACTIVE"
    DUPLICATE_CANDIDATE = "DUPLICATE_CANDIDATE"
    UNCODED_CONCEPT = "UNCODED_CONCEPT"
    PARENT_RETRACTED = "PARENT_RETRACTED"
    RECORD_REJECTED_AT_INGEST = "RECORD_REJECTED_AT_INGEST"


class FlagStatus(StrEnum):
    """A flag's own lifecycle, independent of the record's version (§6.5)."""

    OPEN = "open"
    IN_REVIEW = "in_review"
    RESOLVED = "resolved"
    WONT_FIX = "wont_fix"


class ClinicalStatus(StrEnum):
    """§6.4 — the only field distinguishing history from a current diagnosis."""

    ACTIVE = "active"
    RECURRENCE = "recurrence"
    REMISSION = "remission"
    RESOLVED = "resolved"


class VerificationStatus(StrEnum):
    """§6.4 — independent of ClinicalStatus.

    Without this, "suspected lupus" enters a summary as "has lupus". It is the
    cheapest safeguard in the model against its most expensive error.
    """

    CONFIRMED = "confirmed"
    PROVISIONAL = "provisional"
    DIFFERENTIAL = "differential"
    REFUTED = "refuted"
    UNCONFIRMED = "unconfirmed"


class Interpretation(StrEnum):
    """§9.5 — four states, because a comparator makes a value an interval."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    INDETERMINATE = "indeterminate"


class MeasurementContext(StrEnum):
    """§6.6 — trend analysis must be able to filter on this.

    Home weight and in-clinic weight are never silently averaged.
    """

    CLINICAL = "clinical"
    PATIENT_REPORTED = "patient_reported"
    DEVICE = "device"


class ConsentScope(StrEnum):
    """§6.11 — AI_PROCESSING is the gate for the whole AI layer."""

    TREATMENT = "treatment"
    AI_PROCESSING = "ai_processing"
    DATA_SHARING = "data_sharing"
    RESEARCH = "research"
    FAMILY_ACCESS = "family_access"
