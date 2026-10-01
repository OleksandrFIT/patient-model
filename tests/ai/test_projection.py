from datetime import UTC, date, datetime, timedelta

import pytest

from pai3.ai.artifact import OmissionReason
from pai3.ai.projection import (
    AIPatientView,
    BudgetExceeded,
    ProjectionResult,
    project_patient,
    project_records,
)
from pai3.ai.scope import AIReadScope
from pai3.entities.clinical import AllergyIntolerance, Condition, Criticality
from pai3.entities.people import Patient
from pai3.enums import ClinicalStatus, ProvenanceOrigin, VerificationStatus
from pai3.ids import new_id
from pai3.values.actor import Actor, ActorKind
from pai3.values.codeable import CodeableConcept
from pai3.values.people import HumanName, PatientIdentifier
from pai3.values.provenance import Provenance

NOW = datetime(2026, 3, 12, 9, 0, tzinfo=UTC)
DOC = Actor(kind=ActorKind.HUMAN, ref=new_id("prov"), label="Dr A. Reyes")
PROV = Provenance(origin=ProvenanceOrigin.HUMAN, asserted_by=DOC, asserted_at=NOW)
PATIENT_ID = new_id("pat")
BASE = {"provenance": PROV, "created_at": NOW, "updated_at": NOW, "updated_by": DOC}
SCOPE = AIReadScope(
    patient_id=PATIENT_ID, consent_id=new_id("cons"),
    valid_until=NOW + timedelta(minutes=30), trace_id=new_id("trc"),
)


def _patient() -> Patient:
    return Patient(
        id=PATIENT_ID, **BASE,
        identifiers=[PatientIdentifier(system="emr-west", value="MRN-4471")],
        names=[HumanName(given=["Dana"], family="Okafor")],
        birth_date=date(1979, 4, 2), sex_at_birth="female",
    )


def _condition(status: ClinicalStatus = ClinicalStatus.ACTIVE) -> Condition:
    return Condition(
        id=new_id("cond"), **BASE, patient_id=PATIENT_ID,
        code=CodeableConcept(raw_text="hypothyroidism", system="ICD-10", code="E03.9"),
        clinical_status=status, verification_status=VerificationStatus.CONFIRMED,
    )


def _allergy() -> AllergyIntolerance:
    return AllergyIntolerance(
        id=new_id("alg"), **BASE, patient_id=PATIENT_ID,
        substance=CodeableConcept(raw_text="penicillin", system="RxNorm", code="7980"),
        criticality=Criticality.HIGH, verification_status=VerificationStatus.CONFIRMED,
    )


def test_the_projection_carries_no_identity():
    view = project_patient(_patient(), SCOPE, on=date(2026, 4, 3))
    assert view.age_years == 47
    for forbidden in ("names", "identifiers", "birth_date", "contacts", "addresses"):
        assert forbidden not in AIPatientView.model_fields


def test_projecting_another_patient_through_this_scope_is_refused():
    other = _patient().model_copy(update={"id": new_id("pat")})
    with pytest.raises(PermissionError):
        project_patient(other, SCOPE, on=date(2026, 4, 3))


def test_an_expired_scope_is_refused():
    stale = SCOPE.model_copy(update={"valid_until": NOW - timedelta(minutes=1)})
    with pytest.raises(PermissionError):
        project_patient(_patient(), stale, on=date(2026, 4, 3), now=NOW)


def test_everything_fits_when_the_budget_is_ample():
    result = project_records([_condition(), _allergy()], SCOPE, budget=100)
    assert len(result.included) == 2
    assert result.omitted == []


def test_a_droppable_record_is_omitted_and_named():
    # Resolved conditions are droppable; the omission is reported, never silent.
    result = project_records(
        [_allergy(), _condition(ClinicalStatus.RESOLVED)], SCOPE, budget=1
    )
    assert len(result.omitted) == 1
    assert result.omitted[0].reason is OmissionReason.CONTEXT_BUDGET


def test_a_non_droppable_record_is_never_omitted():
    with pytest.raises(BudgetExceeded):
        project_records([_allergy(), _allergy()], SCOPE, budget=1)


def test_the_error_names_what_would_not_fit():
    with pytest.raises(BudgetExceeded, match="AllergyIntolerance"):
        project_records([_allergy(), _allergy()], SCOPE, budget=1)


def test_active_conditions_are_non_droppable():
    # A narrative without active diagnoses is a list of test results (§10.6).
    with pytest.raises(BudgetExceeded):
        project_records([_condition(), _condition()], SCOPE, budget=1)


def test_the_result_reports_its_budget_usage():
    result = project_records([_condition()], SCOPE, budget=10)
    assert result.budget.limit == 10
    assert result.budget.consumed == 1


def test_omitted_is_required_on_the_result():
    assert ProjectionResult.model_fields["omitted"].is_required()
