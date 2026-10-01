import pytest
from pydantic import ValidationError

from pai3.values.quantity import Quantity, ReferenceRange


def test_value_is_required_inside_quantity():
    # The nonsense state "unit present, value absent" must be unrepresentable.
    with pytest.raises(ValidationError):
        Quantity(unit="mmol/L")


def test_unit_may_be_absent():
    # D5's "missing units must trigger review" — review, not reject.
    assert Quantity(value=7.2).unit is None


def test_comparator_is_restricted_to_four_operators():
    assert Quantity(value=0.01, unit="mIU/L", comparator="<").comparator == "<"
    with pytest.raises(ValidationError):
        Quantity(value=0.01, comparator="~")


def test_is_bounded_reports_a_comparator_result():
    assert Quantity(value=0.01, comparator="<").is_bounded
    assert not Quantity(value=0.01).is_bounded


def test_reference_range_allows_an_open_lower_bound():
    # hs-CRP is reported as 0–3.0; TSH as 0.4–4.0. Both shapes are needed by §9.5.
    assert ReferenceRange(low=0.0, high=3.0).low == 0.0
    assert ReferenceRange(high=3.0).low is None


def test_reference_range_refuses_an_inverted_interval():
    with pytest.raises(ValidationError):
        ReferenceRange(low=4.0, high=0.4)
