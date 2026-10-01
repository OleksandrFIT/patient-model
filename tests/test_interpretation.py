from pai3.enums import Interpretation
from pai3.interpretation import interpret, interpretation_disagrees
from pai3.values.codeable import CodeableConcept
from pai3.values.quantity import Quantity, ReferenceRange

TSH = ReferenceRange(low=0.4, high=4.0)
HS_CRP = ReferenceRange(low=0.0, high=3.0)
NO_UPPER = ReferenceRange(low=0.4)


# --- row 1: no comparator, ordinary comparison
def test_row1_plain_value_below_range_is_low():
    assert interpret(Quantity(value=0.2), TSH) is Interpretation.LOW


def test_row1_plain_value_inside_range_is_normal():
    assert interpret(Quantity(value=2.0), TSH) is Interpretation.NORMAL


def test_row1_plain_value_above_range_is_high():
    assert interpret(Quantity(value=9.0), TSH) is Interpretation.HIGH


# --- row 2: "<x" where x <= low
def test_row2_below_detection_under_the_lower_bound_is_low():
    # TSH <0.01 against 0.4-4.0. Strictly sound: anything below 0.01 is below 0.4.
    assert interpret(Quantity(value=0.01, comparator="<"), TSH) is Interpretation.LOW


# --- row 3: "<x" where low is zero or absent and x <= high
def test_row3_below_detection_with_a_zero_lower_bound_is_normal():
    # hs-CRP <0.3 against 0-3.0. Without this row it returns indeterminate and
    # floods the output with results a physician reads as plainly normal.
    assert interpret(Quantity(value=0.3, comparator="<"), HS_CRP) is Interpretation.NORMAL


def test_row3_applies_when_the_lower_bound_is_absent():
    assert (
        interpret(Quantity(value=0.3, comparator="<"), ReferenceRange(high=3.0))
        is Interpretation.NORMAL
    )


# --- row 4: ">x" where x >= high
def test_row4_above_detection_over_the_upper_bound_is_high():
    assert interpret(Quantity(value=4.0, comparator=">"), TSH) is Interpretation.HIGH


# --- row 5: the interval crosses a boundary
def test_row5_greater_than_inside_the_range_is_indeterminate():
    # >100 against an upper bound of 150: the true value lies in (100, inf).
    rng = ReferenceRange(low=0.0, high=150.0)
    assert (
        interpret(Quantity(value=100.0, comparator=">"), rng) is Interpretation.INDETERMINATE
    )


def test_row5_less_than_crossing_a_real_lower_bound_is_indeterminate():
    # <1.0 against 0.4-4.0 straddles 0.4.
    assert (
        interpret(Quantity(value=1.0, comparator="<"), TSH) is Interpretation.INDETERMINATE
    )


def test_row5_greater_than_with_no_upper_bound_is_indeterminate():
    assert (
        interpret(Quantity(value=9.0, comparator=">"), NO_UPPER)
        is Interpretation.INDETERMINATE
    )


# --- inclusive comparators follow from the same interval reasoning
def test_inclusive_less_than_at_the_bound_is_indeterminate():
    # "<=0.4" includes 0.4, which is itself in range, so "low" is not sound.
    assert (
        interpret(Quantity(value=0.4, comparator="<="), TSH) is Interpretation.INDETERMINATE
    )


def test_inclusive_less_than_below_the_bound_is_low():
    assert interpret(Quantity(value=0.3, comparator="<="), TSH) is Interpretation.LOW


# --- no range at all
def test_without_a_range_nothing_can_be_concluded():
    assert interpret(Quantity(value=2.0), None) is Interpretation.INDETERMINATE


def test_an_empty_range_concludes_nothing():
    assert interpret(Quantity(value=2.0), ReferenceRange()) is Interpretation.INDETERMINATE


# --- reported against computed
def test_disagreement_is_detected():
    reported = CodeableConcept(raw_text="H")
    assert interpretation_disagrees(reported, Interpretation.NORMAL)


def test_agreement_is_not_a_disagreement():
    assert not interpretation_disagrees(CodeableConcept(raw_text="H"), Interpretation.HIGH)


def test_computed_indeterminate_is_not_a_disagreement():
    # Spec §9.5: indeterminate alongside a reported value is not a conflict.
    assert not interpretation_disagrees(
        CodeableConcept(raw_text="H"), Interpretation.INDETERMINATE
    )


def test_absent_reported_value_is_not_a_disagreement():
    assert not interpretation_disagrees(None, Interpretation.HIGH)


def test_an_unrecognised_reported_token_is_not_a_disagreement():
    # We cannot claim a conflict with a token we failed to understand.
    assert not interpretation_disagrees(CodeableConcept(raw_text="??"), Interpretation.HIGH)
