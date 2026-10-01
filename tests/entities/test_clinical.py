from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from pai3.entities.clinical import AllergyIntolerance, Condition, Criticality, Reaction
from pai3.enums import ClinicalStatus, ProvenanceOrigin, VerificationStatus
from pai3.ids import new_id
from pai3.values.actor import Actor, ActorKind
from pai3.values.codeable import CodeableConcept
from pai3.values.provenance import Provenance

NOW = datetime(2026, 3, 12, 9, 0, tzinfo=UTC)
DOC = Actor(kind=ActorKind.HUMAN, ref=new_id("prov"), label="Dr A. Reyes")
PROV = Provenance(origin=ProvenanceOrigin.HUMAN, asserted_by=DOC, asserted_at=NOW)
PATIENT = new_id("pat")


def _base(prefix: str) -> dict:
    return {
        "id": new_id(prefix),
        "provenance": PROV,
        "created_at": NOW,
        "updated_at": NOW,
        "updated_by": DOC,
        "patient_id": PATIENT,
    }


def test_history_and_current_differ_only_by_clinical_status():
    current = Condition(
        **_base("cond"),
        code=CodeableConcept(raw_text="type 2 diabetes", system="ICD-10", code="E11"),
        clinical_status=ClinicalStatus.ACTIVE,
        verification_status=VerificationStatus.CONFIRMED,
    )
    past = current.model_copy(update={"clinical_status": ClinicalStatus.RESOLVED})
    assert current.code == past.code


def test_verification_status_is_independent_of_clinical_status():
    suspected = Condition(
        **_base("cond"),
        code=CodeableConcept(raw_text="lupus"),
        clinical_status=ClinicalStatus.ACTIVE,
        verification_status=VerificationStatus.PROVISIONAL,
    )
    assert suspected.clinical_status is ClinicalStatus.ACTIVE
    assert not suspected.is_assertable


def test_a_confirmed_active_condition_is_assertable():
    condition = Condition(
        **_base("cond"),
        code=CodeableConcept(raw_text="hypertension", system="ICD-10", code="I10"),
        clinical_status=ClinicalStatus.ACTIVE,
        verification_status=VerificationStatus.CONFIRMED,
    )
    assert condition.is_assertable


def test_a_refuted_condition_is_never_assertable():
    condition = Condition(
        **_base("cond"),
        code=CodeableConcept(raw_text="lupus"),
        clinical_status=ClinicalStatus.ACTIVE,
        verification_status=VerificationStatus.REFUTED,
    )
    assert not condition.is_assertable


def test_abatement_before_onset_is_refused():
    with pytest.raises(ValidationError, match="abatement"):
        Condition(
            **_base("cond"),
            code=CodeableConcept(raw_text="flu"),
            clinical_status=ClinicalStatus.RESOLVED,
            verification_status=VerificationStatus.CONFIRMED,
            onset=date(2026, 2, 1),
            abatement=date(2026, 1, 1),
        )


def test_condition_whitelists_clinical_status_for_field_provenance():
    # §6.2: this is exactly where conditions conflict — resolved in the EMR
    # against active in the intake form.
    assert Condition.FIELD_PROVENANCE_WHITELIST == frozenset({"clinical_status"})


def test_criticality_is_separate_from_reaction_severity():
    # §6: "is it life-threatening" is not "how bad was the last reaction".
    allergy = AllergyIntolerance(
        **_base("alg"),
        substance=CodeableConcept(raw_text="penicillin", system="RxNorm", code="7980"),
        criticality=Criticality.HIGH,
        verification_status=VerificationStatus.CONFIRMED,
        reactions=[Reaction(manifestation=CodeableConcept(raw_text="hives"), severity="mild")],
    )
    assert allergy.criticality is Criticality.HIGH
    assert allergy.reactions[0].severity == "mild"


def test_allergy_requires_a_substance():
    with pytest.raises(ValidationError):
        AllergyIntolerance(
            **_base("alg"),
            criticality=Criticality.LOW,
            verification_status=VerificationStatus.CONFIRMED,
        )


def test_an_unconfirmed_allergy_is_not_assertable_but_is_never_dropped():
    # §10.6 makes allergies non-droppable regardless of verification status.
    allergy = AllergyIntolerance(
        **_base("alg"),
        substance=CodeableConcept(raw_text="sulfa"),
        criticality=Criticality.UNABLE_TO_ASSESS,
        verification_status=VerificationStatus.UNCONFIRMED,
    )
    assert not allergy.is_assertable
