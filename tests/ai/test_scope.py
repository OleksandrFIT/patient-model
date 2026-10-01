from datetime import UTC, datetime, timedelta

import pytest

from pai3.ai.scope import AIReadScope, ConsentDenied, authorize_ai_read
from pai3.entities.administrative import Consent
from pai3.enums import ConsentScope, ProvenanceOrigin, RecordStatus
from pai3.ids import new_id
from pai3.values.actor import Actor, ActorKind
from pai3.values.provenance import Provenance

NOW = datetime(2026, 3, 12, 9, 0, tzinfo=UTC)
STAFF = Actor(kind=ActorKind.HUMAN, ref=new_id("prov"), label="M. Chen")
PROV = Provenance(origin=ProvenanceOrigin.HUMAN, asserted_by=STAFF, asserted_at=NOW)
PATIENT = new_id("pat")


def _consent(**over) -> Consent:
    kwargs = {
        "id": new_id("cons"), "provenance": PROV, "created_at": NOW, "updated_at": NOW,
        "updated_by": STAFF, "patient_id": PATIENT, "scope": ConsentScope.AI_PROCESSING,
        "effective_from": NOW - timedelta(days=30),
    }
    return Consent(**(kwargs | over))


def test_an_active_ai_consent_yields_a_scope():
    scope = authorize_ai_read(PATIENT, [_consent()], NOW)
    assert scope.consent_id and scope.trace_id
    assert scope.scope == "ai_processing"


def test_no_consent_raises_rather_than_returning_none():
    # §10.3: None invites `if scope:` and the one caller who omits it.
    with pytest.raises(ConsentDenied):
        authorize_ai_read(PATIENT, [], NOW)


def test_a_treatment_consent_does_not_authorise_ai():
    with pytest.raises(ConsentDenied):
        authorize_ai_read(PATIENT, [_consent(scope=ConsentScope.TREATMENT)], NOW)


def test_a_revoked_consent_is_refused():
    revoked = _consent(revoked_at=NOW - timedelta(days=1), revoked_by=STAFF)
    with pytest.raises(ConsentDenied):
        authorize_ai_read(PATIENT, [revoked], NOW)


def test_an_expired_consent_is_refused():
    with pytest.raises(ConsentDenied):
        authorize_ai_read(PATIENT, [_consent(effective_until=NOW - timedelta(days=1))], NOW)


def test_another_patients_consent_is_refused():
    other = _consent(patient_id=new_id("pat"))
    with pytest.raises(ConsentDenied):
        authorize_ai_read(PATIENT, [other], NOW)


def test_a_retracted_consent_record_is_refused():
    retracted = _consent(record_status=RecordStatus.ENTERED_IN_ERROR)
    with pytest.raises(ConsentDenied):
        authorize_ai_read(PATIENT, [retracted], NOW)


def test_the_scope_bounds_its_own_validity():
    scope = authorize_ai_read(
        PATIENT, [_consent(effective_until=NOW + timedelta(days=1))], NOW
    )
    assert scope.valid_until <= NOW + timedelta(days=1)


def test_an_open_ended_consent_still_bounds_the_scope():
    # A token good forever is a token nobody re-checks.
    scope = authorize_ai_read(PATIENT, [_consent()], NOW)
    assert scope.valid_until > NOW
    assert scope.valid_until <= NOW + timedelta(hours=1)


def test_the_scope_is_still_valid_helper():
    scope = authorize_ai_read(PATIENT, [_consent()], NOW)
    assert scope.is_valid_at(NOW)
    assert not scope.is_valid_at(NOW + timedelta(days=2))


def test_a_scope_cannot_be_built_for_a_patient_it_does_not_name():
    scope = authorize_ai_read(PATIENT, [_consent()], NOW)
    assert scope.patient_id == PATIENT
    assert isinstance(scope, AIReadScope)
