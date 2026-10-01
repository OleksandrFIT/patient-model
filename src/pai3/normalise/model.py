"""The intermediate shapes a normaliser works in.

Nothing here is canonical. A `RawAssertion` is what one source says about one thing, with
enough locator detail to cite it later; a `Conflict` is what two of them disagreeing looks
like before anyone resolves it.

Keeping this layer explicit is what lets §9.3's invariant hold. If sources were merged
directly into entities there would be no object to hold "two values, neither chosen".
"""

from datetime import UTC, date, datetime, time
from enum import StrEnum
from typing import Any

from pydantic import AwareDatetime, BaseModel, Field


class SourceClass(StrEnum):
    """What kind of source a document is, which is what trust is assigned to.

    Not the document, and not the vendor — the class. A lab report is primary for a lab
    value whichever lab issued it; an intake form is self-report whoever typed it up.
    """

    LAB_REPORT = "lab_report"
    EMR = "emr"
    INTAKE = "intake"


class AssertionKind(StrEnum):
    PATIENT = "patient"
    CONDITION = "condition"
    MEDICATION = "medication"
    SUPPLEMENT = "supplement"
    ALLERGY = "allergy"
    LAB = "lab"


class SourceDocument(BaseModel):
    """The source layer: the artifact as received, with a hash (§6.17).

    Immutable. Canonical records cite it through a `SourceReference`; nothing in canonical
    holds its content.
    """

    id: str
    source_class: SourceClass
    filename: str
    content_sha256: str
    received_at: AwareDatetime
    declared_row_count: int | None = Field(
        default=None,
        description="Rows the document itself claims. None means completeness is unverifiable (§9.7)",
    )


class Locator(BaseModel):
    """Where in a document an assertion was found. Becomes a `SourceReference`."""

    document_id: str
    page: int | None = None
    field_path: str | None = None
    quote: str | None = None


class RawAssertion(BaseModel):
    """One claim, from one source, about one thing.

    `key` is what makes two assertions candidates for the same fact. Getting the key wrong
    merges two facts or splits one, so each reader states its own keying rule.
    """

    source_class: SourceClass
    locator: Locator
    kind: AssertionKind
    key: str
    payload: dict[str, Any]
    confidence: float | None = None
    parse_error: str | None = Field(
        default=None, description="Set when the row could not be read at all (§9.7)"
    )

    @property
    def failed(self) -> bool:
        return self.parse_error is not None


class ConflictOutcome(StrEnum):
    AGREED = "agreed"
    RESOLVED_BY_TRUST = "resolved_by_trust"
    UNRESOLVED = "unresolved"
    WINNER_UNREPRESENTABLE = "winner_unrepresentable"
    """A trust rule picked a value the canonical model cannot hold.

    Found while normalising, not anticipated: the patient says she stopped metformin but
    cannot name the month, and §9.8's invariant requires a stop date for a stopped
    medication. The rule says the patient wins; the model says that value is unrepresentable
    without a date. Neither gives way, so canonical keeps the EMR's status and the dispute is
    raised blocking instead of being silently flipped or silently dropped.
    """


class ConflictCandidate(BaseModel):
    """One source's claim about a contested field.

    A list of these rather than a mapping from source class to value. The first version of
    this model used a dict keyed on source class, which silently kept only one of two values
    asserted by the *same* class — exactly the glucose case, where both readings come from
    the lab report. A conflict report that shows one of the two values is worse than none.
    """

    source_class: SourceClass
    value: Any
    locator: Locator
    confidence: float | None = None


class Conflict(BaseModel):
    """Two or more assertions about the same thing that do not agree.

    `winner` is None when no explicit trust rule applies — §9.3 forbids picking one anyway,
    so the canonical field stays empty and this object is the whole record of why.
    """

    kind: AssertionKind
    key: str
    field_name: str
    outcome: ConflictOutcome
    candidates: list[ConflictCandidate]
    winner: SourceClass | None = None
    rule: str | None = Field(default=None, description="Which trust rule decided it, if any")

    @property
    def distinct_values(self) -> list[Any]:
        seen: list[Any] = []
        for c in self.candidates:
            if c.value not in seen:
                seen.append(c.value)
        return seen


class RejectedRow(BaseModel):
    """A row that could not become a canonical record at all (layer 1, §9.1)."""

    locator: Locator
    reason: str
    raw: dict[str, Any]


def as_datetime(value: date | datetime | None) -> datetime | None:
    """Lift a date to midnight UTC so dates and timestamps order together.

    UTC explicitly rather than the local zone: a normalisation run must produce the same
    output on any machine, and a collection date is not a local wall-clock fact.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.combine(value, time(0, 0), tzinfo=UTC)
