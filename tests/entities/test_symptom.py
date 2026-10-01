from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from pai3.entities.clinical import (
    Condition,
    Symptom,
    SymptomReporter,
    SymptomSeverity,
    SymptomStatus,
)
from pai3.enums import ClinicalStatus, ProvenanceOrigin, TextOrigin, VerificationStatus
from pai3.ids import new_id
from pai3.values.actor import Actor, ActorKind
from pai3.values.codeable import CodeableConcept
from pai3.values.provenance import Provenance
from pai3.values.text import ClinicalText

NOW = datetime(2026, 3, 12, 9, 0, tzinfo=UTC)
DOC = Actor(kind=ActorKind.HUMAN, ref=new_id("prov"), label="Dr A. Reyes")
PROV = Provenance(origin=ProvenanceOrigin.HUMAN, asserted_by=DOC, asserted_at=NOW)


def _symptom(**over) -> Symptom:
    kwargs = {
        "id": new_id("sym"), "provenance": PROV, "created_at": NOW, "updated_at": NOW,
        "updated_by": DOC, "patient_id": new_id("pat"),
        "symptom": CodeableConcept(raw_text="fatigue", system="SNOMED-CT", code="84229001"),
        "status": SymptomStatus.ACTIVE,
        "reported_by": SymptomReporter.PATIENT,
    }
    return Symptom(**(kwargs | over))


def test_a_symptom_is_not_a_diagnosis():
    # §6.20: a symptom has no verification_status, because its existence is not in doubt.
    # The patient reports fatigue; whether it means hypothyroidism is a Condition's question.
    assert "verification_status" not in Symptom.model_fields
    assert "verification_status" in Condition.model_fields


def test_a_symptom_records_who_reported_it():
    assert _symptom().reported_by is SymptomReporter.PATIENT
    observed = _symptom(reported_by=SymptomReporter.CLINICIAN_OBSERVED)
    assert observed.reported_by is SymptomReporter.CLINICIAN_OBSERVED


def test_severity_defaults_to_unspecified_rather_than_mild():
    # An unrecorded severity is not a mild one.
    assert _symptom().severity is SymptomSeverity.UNSPECIFIED


def test_a_resolved_symptom_needs_no_date():
    # Same reasoning as Supplement: a patient who says the headache stopped rarely knows
    # when, and demanding the date would discard the fact that it stopped.
    resolved = _symptom(status=SymptomStatus.RESOLVED)
    assert resolved.resolved_on is None
    assert not resolved.is_current


def test_resolution_before_onset_is_refused():
    with pytest.raises(ValidationError, match="resolved_on"):
        _symptom(
            status=SymptomStatus.RESOLVED,
            onset=date(2026, 2, 1),
            resolved_on=date(2026, 1, 1),
        )


def test_an_uncoded_symptom_is_legal():
    # "feeling off" matches nothing, and §6.10 keeps the words rather than guessing a code.
    assert not _symptom(symptom=CodeableConcept(raw_text="feeling off")).symptom.is_coded


def test_a_patient_concern_must_have_crossed_the_perimeter():
    # §10.1: a concern in the patient's own words cannot be practice-authored.
    with pytest.raises(ValidationError, match="patient_concern"):
        _symptom(
            patient_concern=ClinicalText(
                value="Worried this is something serious.",
                origin=TextOrigin.PRACTICE_AUTHORED,
            )
        )


def test_a_patient_concern_is_the_canonical_carrier_for_patient_submitted():
    # This closes the gap §7 named: TextOrigin.PATIENT_SUBMITTED had no canonical field to
    # live on until a symptom could carry the patient's own words.
    symptom = _symptom(
        patient_concern=ClinicalText(
            value="I am worried the tiredness means something is wrong with my heart.",
            origin=TextOrigin.PATIENT_SUBMITTED,
        )
    )
    assert symptom.patient_concern.origin is TextOrigin.PATIENT_SUBMITTED
    assert symptom.patient_concern.crossed_perimeter


def test_a_transcribed_concern_is_also_accepted():
    symptom = _symptom(
        patient_concern=ClinicalText(
            value="Patient said on the phone that she is worried about her heart.",
            origin=TextOrigin.TRANSCRIBED_EXTERNAL,
        )
    )
    assert symptom.patient_concern.crossed_perimeter


def test_a_symptom_and_a_condition_for_one_complaint_stay_separate():
    # The clinical workflow is symptom -> differential -> diagnosis. If fatigue were a
    # Condition, a brief could not tell "reports fatigue" from "has hypothyroidism".
    patient = new_id("pat")
    base = {
        "provenance": PROV, "created_at": NOW, "updated_at": NOW, "updated_by": DOC,
        "patient_id": patient,
    }
    symptom = Symptom(
        id=new_id("sym"), **base,
        symptom=CodeableConcept(raw_text="fatigue", system="SNOMED-CT", code="84229001"),
        status=SymptomStatus.ACTIVE, reported_by=SymptomReporter.PATIENT,
    )
    condition = Condition(
        id=new_id("cond"), **base,
        code=CodeableConcept(raw_text="hypothyroidism", system="ICD-10", code="E03.9"),
        clinical_status=ClinicalStatus.ACTIVE,
        verification_status=VerificationStatus.CONFIRMED,
    )
    assert symptom.id != condition.id
    assert condition.is_assertable
    assert symptom.is_current
