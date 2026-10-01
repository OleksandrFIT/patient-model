"""The clinical timeline — derived, never stored (§6.13).

A projection over encounters, condition onset and abatement, medication start and stop,
labs, procedures and notes. Storing it would create a second source of truth that goes
stale the moment any entity changes, with nothing to detect the divergence.

`TimelineEvent` has no `id` and no provenance of its own: it is a view of a record, and
every row names the record it came from so a reader can go back to the vouched-for fact.
"""

from datetime import UTC, date, datetime, time
from enum import StrEnum

from pydantic import AwareDatetime, BaseModel

from pai3.entities.clinical import Condition, Encounter, Procedure, SocialFactor
from pai3.entities.narrative import ClinicalNote
from pai3.entities.results import DiagnosticReport, LabResult
from pai3.entities.therapy import Medication, Supplement

MIDNIGHT = time(0, 0)
"""A date-only fact is ordered at midnight UTC: enough to place it, and honest about
the precision it actually has."""


class EventKind(StrEnum):
    ENCOUNTER = "encounter"
    CONDITION_ONSET = "condition_onset"
    CONDITION_RESOLVED = "condition_resolved"
    MEDICATION_STARTED = "medication_started"
    MEDICATION_STOPPED = "medication_stopped"
    SUPPLEMENT_STARTED = "supplement_started"
    SUPPLEMENT_STOPPED = "supplement_stopped"
    LAB_COLLECTED = "lab_collected"
    REPORT_ISSUED = "report_issued"
    PROCEDURE = "procedure"
    NOTE_AUTHORED = "note_authored"
    SOCIAL_FACTOR_ASSERTED = "social_factor_asserted"


class TimelineEvent(BaseModel):
    at: AwareDatetime
    kind: EventKind
    label: str
    source_type: str
    source_id: str


def _as_datetime(value: date | datetime) -> datetime:
    """Lift a date to an aware datetime so dates and timestamps can be ordered together."""
    if isinstance(value, datetime):
        return value
    return datetime.combine(value, MIDNIGHT, tzinfo=UTC)


def build_timeline(
    *,
    encounters: list[Encounter] | None = None,
    conditions: list[Condition] | None = None,
    medications: list[Medication] | None = None,
    supplements: list[Supplement] | None = None,
    labs: list[LabResult] | None = None,
    reports: list[DiagnosticReport] | None = None,
    procedures: list[Procedure] | None = None,
    notes: list[ClinicalNote] | None = None,
    social_factors: list[SocialFactor] | None = None,
) -> list[TimelineEvent]:
    """Project the dated facts of a chart into one ordered sequence.

    A record with no usable date contributes nothing. Inventing one to make it appear
    would put a fact on the timeline at a moment nobody vouched for.
    """
    events: list[TimelineEvent] = []

    def add(at: date | datetime | None, kind: EventKind, label: str, record: object) -> None:
        if at is None:
            return
        events.append(
            TimelineEvent(
                at=_as_datetime(at),
                kind=kind,
                label=label,
                source_type=type(record).__name__,
                source_id=record.id,
            )
        )

    for enc in encounters or []:
        add(enc.started_at, EventKind.ENCOUNTER, enc.encounter_type, enc)
    for cond in conditions or []:
        add(cond.onset, EventKind.CONDITION_ONSET, cond.code.raw_text, cond)
        add(cond.abatement, EventKind.CONDITION_RESOLVED, cond.code.raw_text, cond)
    for med in medications or []:
        add(med.started_on, EventKind.MEDICATION_STARTED, med.drug.raw_text, med)
        add(med.stopped_on, EventKind.MEDICATION_STOPPED, med.drug.raw_text, med)
    for supp in supplements or []:
        add(supp.started_on, EventKind.SUPPLEMENT_STARTED, supp.substance.raw_text, supp)
        add(supp.stopped_on, EventKind.SUPPLEMENT_STOPPED, supp.substance.raw_text, supp)
    for lab in labs or []:
        add(lab.collection_date, EventKind.LAB_COLLECTED, lab.biomarker.raw_text, lab)
    for report in reports or []:
        add(report.issued_at, EventKind.REPORT_ISSUED, report.report_type.raw_text, report)
    for proc in procedures or []:
        add(proc.performed_on, EventKind.PROCEDURE, proc.code.raw_text, proc)
    for note in notes or []:
        add(note.authored_at, EventKind.NOTE_AUTHORED, note.note_type.value, note)
    for factor in social_factors or []:
        add(
            factor.asserted_on, EventKind.SOCIAL_FACTOR_ASSERTED,
            f"{factor.factor.raw_text}: {factor.value}", factor,
        )

    return sorted(events, key=lambda e: e.at)
