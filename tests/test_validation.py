from datetime import UTC, date, datetime

from pai3.entities.clinical import Condition
from pai3.entities.results import LabResult
from pai3.entities.therapy import Medication, MedicationStatus
from pai3.enums import (
    ClinicalStatus,
    FlagCode,
    ProvenanceOrigin,
    Severity,
    VerificationStatus,
)
from pai3.ids import new_id
from pai3.validation import check_condition, check_lab_result, check_medication
from pai3.values.actor import Actor, ActorKind
from pai3.values.codeable import CodeableConcept
from pai3.values.dosage import Dosage
from pai3.values.provenance import Provenance
from pai3.values.quantity import Quantity, ReferenceRange

NOW = datetime(2026, 3, 12, 9, 0, tzinfo=UTC)
DOC = Actor(kind=ActorKind.HUMAN, ref=new_id("prov"), label="Dr A. Reyes")
PROV = Provenance(origin=ProvenanceOrigin.HUMAN, asserted_by=DOC, asserted_at=NOW)
BASE = {"provenance": PROV, "created_at": NOW, "updated_at": NOW, "updated_by": DOC}


def _lab(**over) -> LabResult:
    kwargs = {
        "id": new_id("lab"), **BASE, "patient_id": new_id("pat"),
        "biomarker": CodeableConcept(raw_text="TSH", system="LOINC", code="3016-3"),
        "collection_date": NOW,
    }
    return LabResult(**(kwargs | over))


def _codes(flags) -> set[FlagCode]:
    return {f.code for f in flags}


def test_a_complete_lab_raises_nothing():
    lab = _lab(
        quantity=Quantity(value=2.1, unit="mIU/L"),
        reference_range=ReferenceRange(low=0.4, high=4.0),
    )
    assert check_lab_result(lab, DOC, NOW) == []


def test_a_missing_unit_is_human_review_required():
    flags = check_lab_result(_lab(quantity=Quantity(value=2.1)), DOC, NOW)
    assert FlagCode.MISSING_UNIT in _codes(flags)
    assert all(
        f.severity is Severity.HUMAN_REVIEW_REQUIRED
        for f in flags
        if f.code is FlagCode.MISSING_UNIT
    )


def test_a_missing_reference_range_is_a_warning():
    flags = check_lab_result(_lab(quantity=Quantity(value=2.1, unit="mIU/L")), DOC, NOW)
    missing = [f for f in flags if f.code is FlagCode.MISSING_REFERENCE_RANGE]
    assert missing and missing[0].severity is Severity.WARNING


def test_an_uncoded_biomarker_is_human_review_required():
    lab = _lab(
        biomarker=CodeableConcept(raw_text="thyroid thing"),
        quantity=Quantity(value=2.1, unit="mIU/L"),
        reference_range=ReferenceRange(low=0.4, high=4.0),
    )
    assert FlagCode.UNCODED_CONCEPT in _codes(check_lab_result(lab, DOC, NOW))


def test_interpretation_disagreement_is_flagged():
    lab = _lab(
        quantity=Quantity(value=2.1, unit="mIU/L"),
        reference_range=ReferenceRange(low=0.4, high=4.0),
        reported_interpretation=CodeableConcept(raw_text="H"),
    )
    assert FlagCode.INTERPRETATION_DISAGREES_WITH_RANGE in _codes(
        check_lab_result(lab, DOC, NOW)
    )


def test_agreement_is_not_flagged():
    lab = _lab(
        quantity=Quantity(value=9.0, unit="mIU/L"),
        reference_range=ReferenceRange(low=0.4, high=4.0),
        reported_interpretation=CodeableConcept(raw_text="H"),
    )
    assert FlagCode.INTERPRETATION_DISAGREES_WITH_RANGE not in _codes(
        check_lab_result(lab, DOC, NOW)
    )


def test_an_empty_value_slot_is_not_itself_flagged_here():
    # The flag for an unresolved conflict is raised by the normaliser that found the
    # conflict, with both candidates attached (§9.3). Absence alone proves nothing.
    assert FlagCode.CONFLICTING_VALUES not in _codes(check_lab_result(_lab(), DOC, NOW))


def test_an_uncoded_condition_is_flagged():
    condition = Condition(
        id=new_id("cond"), **BASE, patient_id=new_id("pat"),
        code=CodeableConcept(raw_text="high bp"),
        clinical_status=ClinicalStatus.ACTIVE,
        verification_status=VerificationStatus.CONFIRMED,
    )
    assert FlagCode.UNCODED_CONCEPT in _codes(check_condition(condition, DOC, NOW))


def test_a_stopped_medication_with_no_prescriber_is_not_flagged_as_active():
    med = Medication(
        id=new_id("med"), **BASE, patient_id=new_id("pat"),
        drug=CodeableConcept(raw_text="metformin", system="RxNorm", code="6809"),
        dosage=Dosage(text="500 mg BID"),
        status=MedicationStatus.STOPPED, stopped_on=date(2026, 1, 9),
    )
    assert FlagCode.DISCONTINUED_SHOWN_ACTIVE not in _codes(check_medication(med, DOC, NOW))


def test_an_active_medication_with_an_unparsed_dose_is_flagged_for_review():
    med = Medication(
        id=new_id("med"), **BASE, patient_id=new_id("pat"),
        drug=CodeableConcept(raw_text="metformin", system="RxNorm", code="6809"),
        dosage=Dosage(text="as directed"),
        status=MedicationStatus.ACTIVE,
    )
    flags = check_medication(med, DOC, NOW)
    assert FlagCode.MISSING_UNIT in _codes(flags)
