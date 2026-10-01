import pytest
from pydantic import ValidationError

from pai3.ids import new_id
from pai3.values.actor import Actor, ActorKind
from pai3.values.people import Address, ContactPoint, HumanName, PatientIdentifier


def test_actor_distinguishes_kinds():
    human = Actor(kind=ActorKind.HUMAN, ref=new_id("prov"), label="Dr A. Reyes")
    agent = Actor(kind=ActorKind.AGENT, ref="brief-agent", label="brief-agent")
    assert human.kind is not agent.kind


def test_actor_requires_a_ref():
    # An actor without a ref cannot be held accountable, which defeats the point.
    with pytest.raises(ValidationError):
        Actor(kind=ActorKind.HUMAN, ref="", label="x")


def test_patient_identifier_keeps_its_assigning_system():
    # Spec §6.12: one patient has several MRNs across source systems.
    ident = PatientIdentifier(system="emr-west", value="MRN-4471", assigner="West Clinic")
    assert ident.system == "emr-west"


def test_human_name_keeps_the_parts_separately():
    name = HumanName(given=["Dana"], family="Okafor")
    assert name.family == "Okafor"


def test_contact_point_and_address_construct():
    assert ContactPoint(system="phone", value="+1-555-0100", use="mobile").use == "mobile"
    assert Address(lines=["12 Rue Haute"], city="Lyon", country="FR").city == "Lyon"
