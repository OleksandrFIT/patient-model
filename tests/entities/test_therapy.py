from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from pai3.entities.therapy import Medication, MedicationStatus
from pai3.enums import ProvenanceOrigin
from pai3.ids import new_id
from pai3.values.actor import Actor, ActorKind
from pai3.values.codeable import CodeableConcept
from pai3.values.dosage import Dosage
from pai3.values.provenance import Provenance

NOW = datetime(2026, 3, 12, 9, 0, tzinfo=UTC)
DOC = Actor(kind=ActorKind.HUMAN, ref=new_id("prov"), label="Dr A. Reyes")
PROV = Provenance(origin=ProvenanceOrigin.HUMAN, asserted_by=DOC, asserted_at=NOW)


def _med(**over) -> Medication:
    kwargs = {
        "id": new_id("med"),
        "provenance": PROV,
        "created_at": NOW,
        "updated_at": NOW,
        "updated_by": DOC,
        "patient_id": new_id("pat"),
        "drug": CodeableConcept(raw_text="metformin", system="RxNorm", code="6809"),
        "dosage": Dosage(text="500 mg BID", amount=500.0, unit="mg", frequency="BID"),
        "status": MedicationStatus.ACTIVE,
    }
    return Medication(**(kwargs | over))


def test_an_active_medication_is_current():
    assert _med().is_current


def test_a_stopped_medication_is_not_current():
    # D5: discontinued medications must not be treated as active without review.
    assert not _med(status=MedicationStatus.STOPPED, stopped_on=date(2026, 1, 9)).is_current


def test_a_stopped_medication_needs_a_stop_date():
    with pytest.raises(ValidationError, match="stopped_on"):
        _med(status=MedicationStatus.STOPPED)


def test_a_stop_date_on_an_active_medication_is_refused():
    # This is exactly the "discontinued shown as active" defect, caught at layer 1.
    with pytest.raises(ValidationError, match="stopped_on"):
        _med(status=MedicationStatus.ACTIVE, stopped_on=date(2026, 1, 9))


def test_stop_before_start_is_refused():
    with pytest.raises(ValidationError, match="stopped_on"):
        _med(
            status=MedicationStatus.STOPPED,
            started_on=date(2026, 2, 1),
            stopped_on=date(2026, 1, 1),
        )


def test_dose_and_status_are_the_whitelist():
    assert Medication.FIELD_PROVENANCE_WHITELIST == frozenset({"dose", "status"})


def test_prescriber_is_a_provider_reference_not_a_name():
    med = _med(prescriber_id=new_id("prov"))
    assert med.prescriber_id.startswith("prov_")
