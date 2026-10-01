from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from pai3.entities.people import CareTeamMembership, Patient
from pai3.enums import ProvenanceOrigin
from pai3.ids import new_id
from pai3.values.actor import Actor, ActorKind
from pai3.values.people import Address, ContactPoint, HumanName, PatientIdentifier
from pai3.values.provenance import Provenance

NOW = datetime(2026, 3, 12, 9, 0, tzinfo=UTC)
STAFF = Actor(kind=ActorKind.HUMAN, ref=new_id("prov"), label="M. Chen")
PROV = Provenance(origin=ProvenanceOrigin.HUMAN, asserted_by=STAFF, asserted_at=NOW)


def _patient(**over) -> Patient:
    kwargs = {
        "id": new_id("pat"),
        "provenance": PROV,
        "created_at": NOW,
        "updated_at": NOW,
        "updated_by": STAFF,
        "names": [HumanName(given=["Dana"], family="Okafor")],
        "birth_date": date(1979, 4, 2),
        "sex_at_birth": "female",
        "identifiers": [PatientIdentifier(system="emr-west", value="MRN-4471")],
    }
    return Patient(**(kwargs | over))


def test_patient_holds_several_identifiers():
    patient = _patient(
        identifiers=[
            PatientIdentifier(system="emr-west", value="MRN-4471"),
            PatientIdentifier(system="lab-portal", value="LP-99812"),
        ]
    )
    assert len(patient.identifiers) == 2


def test_at_least_one_identifier_is_required():
    # D5: "Patient must have a durable patient identifier" — a layer-1 invariant.
    with pytest.raises(ValidationError, match="identifier"):
        _patient(identifiers=[])


def test_at_least_one_name_is_required():
    with pytest.raises(ValidationError):
        _patient(names=[])


def test_patient_is_not_patient_scoped():
    # Its own id is the scope (§2.4).
    assert "patient_id" not in Patient.model_fields


def test_age_is_derived_not_stored():
    # §10.4 gives the AI projection age and not date of birth.
    patient = _patient(birth_date=date(1979, 4, 2))
    assert patient.age_years(datetime(2026, 4, 1, tzinfo=UTC).date()) == 46
    assert patient.age_years(datetime(2026, 4, 2, tzinfo=UTC).date()) == 47


def test_contacts_and_addresses_are_embedded_lists():
    patient = _patient(
        contacts=[ContactPoint(system="phone", value="+1-555-0100")],
        addresses=[Address(lines=["12 Rue Haute"], city="Lyon", country="FR")],
    )
    assert patient.contacts and patient.addresses


def test_care_team_membership_marks_the_primary():
    patient = _patient(
        care_team=[
            CareTeamMembership(provider_id=new_id("prov"), role="internist", is_primary=True)
        ]
    )
    assert patient.care_team[0].is_primary
