import pytest
from pydantic import ValidationError

from pai3.enums import FlagCode, Severity
from pai3.ids import new_id
from pai3.values.dosage import Dosage
from pai3.values.flags import FlagSummary
from pai3.values.plan import PlanItem


def test_dosage_keeps_the_text_as_given():
    # A supplement arrives as "one dropper", which no structured field accepts.
    assert Dosage(text="one dropper twice daily").text == "one dropper twice daily"


def test_dosage_structured_parts_are_optional():
    dose = Dosage(text="500 mg BID", amount=500.0, unit="mg", frequency="BID", route="oral")
    assert dose.amount == 500.0


def test_dosage_requires_some_text():
    with pytest.raises(ValidationError):
        Dosage(text="")


def test_plan_item_may_reference_a_canonical_record():
    item = PlanItem(description="Titrate metformin", targets=[new_id("med")])
    assert item.targets


def test_flag_summary_carries_code_and_severity():
    summary = FlagSummary(
        flag_id=new_id("flag"),
        code=FlagCode.CONFLICTING_VALUES,
        severity=Severity.BLOCKING,
        message="glucose: EMR 5.5 against lab 7.2, unresolved",
    )
    assert summary.severity is Severity.BLOCKING


def test_flag_summary_message_is_required():
    # A summary with no message cannot be rendered to a physician, which is its job.
    with pytest.raises(ValidationError):
        FlagSummary(
            flag_id=new_id("flag"),
            code=FlagCode.MISSING_UNIT,
            severity=Severity.HUMAN_REVIEW_REQUIRED,
            message="",
        )
