from datetime import UTC, date, datetime, timedelta

from pai3.entities.clinical import Condition, Encounter, Procedure
from pai3.entities.narrative import ClinicalNote, NoteType
from pai3.entities.results import LabResult
from pai3.entities.therapy import Medication, MedicationStatus
from pai3.enums import ClinicalStatus, ProvenanceOrigin, TextOrigin, VerificationStatus
from pai3.ids import new_id
from pai3.readmodels.timeline import EventKind, build_timeline
from pai3.values.actor import Actor, ActorKind
from pai3.values.codeable import CodeableConcept
from pai3.values.dosage import Dosage
from pai3.values.provenance import Provenance
from pai3.values.quantity import Quantity
from pai3.values.text import ClinicalText

NOW = datetime(2026, 3, 12, 9, 0, tzinfo=UTC)
DOC = Actor(kind=ActorKind.HUMAN, ref=new_id("prov"), label="Dr A")
PROV = Provenance(origin=ProvenanceOrigin.HUMAN, asserted_by=DOC, asserted_at=NOW)
PATIENT = new_id("pat")
B = lambda p: {
    "id": new_id(p), "provenance": PROV, "created_at": NOW, "updated_at": NOW,
    "updated_by": DOC, "patient_id": PATIENT,
}


def _condition(onset: date, abatement: date | None = None) -> Condition:
    return Condition(
        **B("cond"), code=CodeableConcept(raw_text="hypothyroidism"),
        clinical_status=ClinicalStatus.RESOLVED if abatement else ClinicalStatus.ACTIVE,
        verification_status=VerificationStatus.CONFIRMED,
        onset=onset, abatement=abatement,
    )


def test_a_condition_with_an_abatement_yields_two_events():
    events = build_timeline(conditions=[_condition(date(2019, 2, 3), date(2019, 11, 20))])
    kinds = [e.kind for e in events]
    assert kinds == [EventKind.CONDITION_ONSET, EventKind.CONDITION_RESOLVED]


def test_a_condition_with_no_abatement_yields_one():
    assert len(build_timeline(conditions=[_condition(date(2021, 5, 14))])) == 1


def test_a_condition_with_no_onset_yields_nothing():
    # An undated fact cannot be placed, and inventing a date would be worse.
    undated = Condition(
        **B("cond"), code=CodeableConcept(raw_text="hypothyroidism"),
        clinical_status=ClinicalStatus.ACTIVE,
        verification_status=VerificationStatus.CONFIRMED,
    )
    assert build_timeline(conditions=[undated]) == []


def test_events_come_back_in_chronological_order():
    events = build_timeline(
        conditions=[_condition(date(2021, 5, 14)), _condition(date(2019, 2, 3))]
    )
    assert [e.at.year for e in events] == [2019, 2021]


def test_every_event_names_the_record_it_came_from():
    # The timeline is a projection, so each row must be traceable back (§6.13).
    events = build_timeline(conditions=[_condition(date(2021, 5, 14))])
    assert events[0].source_id.startswith("cond_")
    assert events[0].source_type == "Condition"


def test_each_source_kind_contributes_its_events():
    cond = _condition(date(2021, 5, 14))
    enc = Encounter(
        **B("enc"), encounter_type="office visit", started_at=NOW - timedelta(days=1)
    )
    med = Medication(
        **B("med"), drug=CodeableConcept(raw_text="levothyroxine"),
        dosage=Dosage(text="75 mcg"), status=MedicationStatus.STOPPED,
        started_on=date(2021, 6, 1), stopped_on=date(2025, 1, 9),
    )
    lab = LabResult(
        **B("lab"), biomarker=CodeableConcept(raw_text="TSH"),
        collection_date=NOW - timedelta(days=14), quantity=Quantity(value=5.6, unit="mIU/L"),
    )
    proc = Procedure(
        **B("proc"), code=CodeableConcept(raw_text="thyroid ultrasound"),
        performed_on=date(2026, 3, 1),
    )
    note = ClinicalNote(
        **B("note"), note_type=NoteType.PROGRESS, authored_at=NOW, author_id=DOC.ref,
        body=ClinicalText(value="Discussed dose.", origin=TextOrigin.PRACTICE_AUTHORED),
    )
    events = build_timeline(
        conditions=[cond], encounters=[enc], medications=[med],
        labs=[lab], procedures=[proc], notes=[note],
    )
    assert {e.kind for e in events} == {
        EventKind.CONDITION_ONSET,
        EventKind.ENCOUNTER,
        EventKind.MEDICATION_STARTED,
        EventKind.MEDICATION_STOPPED,
        EventKind.LAB_COLLECTED,
        EventKind.PROCEDURE,
        EventKind.NOTE_AUTHORED,
    }


def test_the_timeline_is_not_an_entity():
    # §6.13: stored, it becomes a second source of truth that goes stale silently.
    from pai3 import entities
    from pai3.readmodels.timeline import TimelineEvent

    assert not hasattr(entities, "TimelineEvent")
    assert "id" not in TimelineEvent.model_fields
