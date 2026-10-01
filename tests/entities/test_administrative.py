from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from pai3.entities.administrative import Consent
from pai3.entities.clinical import Encounter
from pai3.enums import ConsentScope, ProvenanceOrigin
from pai3.ids import new_id
from pai3.values.actor import Actor, ActorKind
from pai3.values.provenance import Provenance

NOW = datetime(2026, 3, 12, 9, 0, tzinfo=UTC)
STAFF = Actor(kind=ActorKind.HUMAN, ref=new_id("prov"), label="M. Chen")
PROV = Provenance(origin=ProvenanceOrigin.HUMAN, asserted_by=STAFF, asserted_at=NOW)
BASE = {"provenance": PROV, "created_at": NOW, "updated_at": NOW, "updated_by": STAFF}


def _consent(**over) -> Consent:
    kwargs = {
        "id": new_id("cons"), **BASE, "patient_id": new_id("pat"),
        "scope": ConsentScope.AI_PROCESSING,
        "effective_from": NOW - timedelta(days=30),
    }
    return Consent(**(kwargs | over))


def test_an_open_ended_consent_is_active():
    assert _consent().is_active_at(NOW)


def test_a_consent_not_yet_in_force_is_inactive():
    assert not _consent(effective_from=NOW + timedelta(days=1)).is_active_at(NOW)


def test_an_expired_consent_is_inactive():
    assert not _consent(effective_until=NOW - timedelta(days=1)).is_active_at(NOW)


def test_a_revoked_consent_is_inactive_even_inside_its_window():
    consent = _consent(revoked_at=NOW - timedelta(days=1), revoked_by=STAFF)
    assert not consent.is_active_at(NOW)


def test_revocation_requires_who_revoked_it():
    with pytest.raises(ValidationError, match="revoked_by"):
        _consent(revoked_at=NOW)


def test_revocation_before_the_window_opens_is_refused():
    with pytest.raises(ValidationError, match="revoked_at"):
        _consent(effective_from=NOW, revoked_at=NOW - timedelta(days=5), revoked_by=STAFF)


def test_consent_has_no_encounter_field():
    # §2.4: Consent is PatientScoped, not ClinicalRecord.
    assert "encounter_id" not in Consent.model_fields


def test_encounter_is_patient_scoped_not_clinical():
    # It *is* the encounter; it does not reference itself.
    assert "encounter_id" not in Encounter.model_fields


def test_encounter_period_must_not_end_before_it_starts():
    with pytest.raises(ValidationError, match="ended_at"):
        Encounter(
            id=new_id("enc"), **BASE, patient_id=new_id("pat"),
            encounter_type="office visit",
            started_at=NOW, ended_at=NOW - timedelta(hours=1),
        )
