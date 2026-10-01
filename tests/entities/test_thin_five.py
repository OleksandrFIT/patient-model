from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from pai3.entities.administrative import Coverage
from pai3.entities.clinical import Goal, Procedure, SocialFactor
from pai3.entities.workflow import Task, TaskOrigin, TaskStatus
from pai3.enums import ProvenanceOrigin
from pai3.ids import new_id
from pai3.values.actor import Actor, ActorKind
from pai3.values.codeable import CodeableConcept
from pai3.values.provenance import Provenance

NOW = datetime(2026, 3, 12, 9, 0, tzinfo=UTC)
STAFF = Actor(kind=ActorKind.HUMAN, ref=new_id("prov"), label="M. Chen")
PROV = Provenance(origin=ProvenanceOrigin.HUMAN, asserted_by=STAFF, asserted_at=NOW)
BASE = {"provenance": PROV, "created_at": NOW, "updated_at": NOW, "updated_by": STAFF}
PATIENT = new_id("pat")


def test_coverage_carries_effective_dates():
    # Concierge practices bill labs through insurance even when membership is self-pay.
    coverage = Coverage(
        id=new_id("cov"), **BASE, patient_id=PATIENT, payer="Meridian Health",
        member_id="MH-88213", effective_from=date(2026, 1, 1),
    )
    assert coverage.payer == "Meridian Health"


def test_goal_is_patient_scoped_with_no_encounter():
    # A goal can exist before any plan and before any visit (§2.4).
    assert "encounter_id" not in Goal.model_fields
    goal = Goal(
        id=new_id("goal"), **BASE, patient_id=PATIENT,
        description="Come off metformin within a year",
    )
    assert goal.status == "active"


def test_social_factor_records_when_it_was_asserted():
    # Its risk is staleness, so a record with a date beats a mutable block (§6.16).
    factor = SocialFactor(
        id=new_id("soc"), **BASE, patient_id=PATIENT,
        factor=CodeableConcept(raw_text="smoking status"), value="former smoker",
        asserted_on=date(2019, 6, 1),
    )
    assert factor.asserted_on.year == 2019


def test_procedure_requires_a_performed_date():
    with pytest.raises(ValidationError):
        Procedure(
            id=new_id("proc"), **BASE, patient_id=PATIENT,
            code=CodeableConcept(raw_text="colonoscopy"),
        )


def test_an_ai_suggested_task_lands_proposed():
    # §4: AI-extracted tasks land proposed, never open and assigned.
    task = Task(
        id=new_id("task"), **BASE, patient_id=PATIENT,
        description="Repeat TSH in six weeks", origin=TaskOrigin.AI_SUGGESTED,
    )
    assert task.status is TaskStatus.PROPOSED


def test_an_ai_suggested_task_may_not_be_opened_and_assigned():
    with pytest.raises(ValidationError, match="ai_suggested"):
        Task(
            id=new_id("task"), **BASE, patient_id=PATIENT,
            description="Repeat TSH", origin=TaskOrigin.AI_SUGGESTED,
            status=TaskStatus.OPEN, assignee_id=new_id("prov"),
        )


def test_a_human_task_may_open_assigned():
    task = Task(
        id=new_id("task"), **BASE, patient_id=PATIENT, description="Call patient",
        origin=TaskOrigin.HUMAN, status=TaskStatus.OPEN, assignee_id=new_id("prov"),
    )
    assert task.status is TaskStatus.OPEN
