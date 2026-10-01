from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from pai3.entities.therapy import Supplement, SupplementStatus, TreatmentPlan
from pai3.enums import ProvenanceOrigin
from pai3.ids import new_id
from pai3.values.actor import Actor, ActorKind
from pai3.values.codeable import CodeableConcept
from pai3.values.dosage import Dosage
from pai3.values.plan import PlanItem
from pai3.values.provenance import Provenance

NOW = datetime(2026, 3, 12, 9, 0, tzinfo=UTC)
PATIENT_ACTOR = Actor(kind=ActorKind.HUMAN, ref=new_id("pat"), label="Dana Okafor")
PROV = Provenance(origin=ProvenanceOrigin.HUMAN, asserted_by=PATIENT_ACTOR, asserted_at=NOW)
BASE = {
    "provenance": PROV,
    "created_at": NOW,
    "updated_at": NOW,
    "updated_by": PATIENT_ACTOR,
}


def test_a_supplement_accepts_an_unparseable_dose():
    # "one dropper" has no mg. Refusing it loses the fact that it is being taken.
    supp = Supplement(
        id=new_id("supp"), **BASE, patient_id=new_id("pat"),
        substance=CodeableConcept(raw_text="vitamin D3"),
        dosage=Dosage(text="one dropper daily"),
        status=SupplementStatus.ACTIVE,
    )
    assert supp.dosage.amount is None


def test_a_supplement_has_no_prescriber_field():
    # §6.7: the trust presumption differs — a supplement is self-reported.
    assert "prescriber_id" not in Supplement.model_fields


def test_treatment_plan_embeds_its_items():
    plan = TreatmentPlan(
        id=new_id("plan"), **BASE, patient_id=new_id("pat"), title="Q2 metabolic plan",
        items=[PlanItem(description="Titrate metformin", targets=[new_id("med")])],
    )
    assert plan.items[0].description == "Titrate metformin"


def test_a_plan_needs_at_least_one_item():
    with pytest.raises(ValidationError):
        TreatmentPlan(
            id=new_id("plan"), **BASE, patient_id=new_id("pat"), title="empty", items=[]
        )
