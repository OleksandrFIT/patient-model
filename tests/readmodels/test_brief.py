from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from pai3.enums import FlagCode, Severity
from pai3.ids import new_id
from pai3.readmodels.brief import PatientHeader, PreVisitBrief
from pai3.values.flags import FlagSummary

NOW = datetime(2026, 3, 12, 9, 0, tzinfo=UTC)
HEADER = PatientHeader(
    patient_id=new_id("pat"), display_name="Dana Okafor",
    primary_mrn="MRN-4471", birth_date=date(1979, 4, 2),
)


def test_identity_sits_on_the_deterministic_header():
    # §10.4: the practice assembles this; the narrative never receives it.
    assert HEADER.display_name == "Dana Okafor"
    assert HEADER.primary_mrn == "MRN-4471"


def test_unresolved_is_required_with_no_default():
    # §9.4: a brief that dropped a flagged lab must be impossible to construct.
    assert PreVisitBrief.model_fields["unresolved"].is_required()
    with pytest.raises(ValidationError):
        PreVisitBrief(header=HEADER, generated_at=NOW)


def test_an_empty_unresolved_list_must_be_passed_deliberately():
    brief = PreVisitBrief(header=HEADER, generated_at=NOW, unresolved=[])
    assert brief.unresolved == []
    assert brief.narrative is None


def test_a_brief_without_a_narrative_states_why():
    # §10.6: refusal rather than truncation, and the reason reaches the physician.
    brief = PreVisitBrief(
        header=HEADER, generated_at=NOW, unresolved=[],
        narrative_withheld_reason="non-droppable records exceed the context budget",
    )
    assert brief.narrative is None
    assert "budget" in brief.narrative_withheld_reason


def test_a_blocking_flag_is_carried_to_the_reader():
    flag = FlagSummary(
        flag_id=new_id("flag"), code=FlagCode.CONFLICTING_VALUES,
        severity=Severity.BLOCKING,
        message="glucose: EMR 5.5 against lab 7.2, unresolved",
    )
    brief = PreVisitBrief(header=HEADER, generated_at=NOW, unresolved=[flag])
    assert brief.has_blocking_flags
    assert "7.2" in brief.unresolved[0].message


def test_a_brief_with_no_flags_reports_none():
    assert not PreVisitBrief(
        header=HEADER, generated_at=NOW, unresolved=[]
    ).has_blocking_flags


def test_the_brief_has_no_context_budget():
    # §10.6: the deterministic brief holds everything; only the narrative is bounded.
    assert "budget" not in PreVisitBrief.model_fields
