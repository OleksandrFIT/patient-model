from datetime import UTC, datetime, timedelta

from pai3.entities.results import LabResult
from pai3.enums import ProvenanceOrigin
from pai3.ids import new_id
from pai3.readmodels.trend import Direction, ExclusionReason, LabTrend, build_lab_trend
from pai3.values.actor import Actor, ActorKind
from pai3.values.codeable import CodeableConcept
from pai3.values.provenance import Provenance
from pai3.values.quantity import Quantity

NOW = datetime(2026, 3, 12, 9, 0, tzinfo=UTC)
LAB = Actor(kind=ActorKind.SYSTEM, ref="lab-portal", label="lab-portal")
PROV = Provenance(origin=ProvenanceOrigin.SOURCE_SYSTEM, asserted_by=LAB, asserted_at=NOW)
TSH = CodeableConcept(raw_text="TSH", system="LOINC", code="3016-3")


def _lab(value: float | None, days_ago: int, unit: str | None = "mIU/L", comparator=None):
    return LabResult(
        id=new_id("lab"), provenance=PROV, created_at=NOW, updated_at=NOW, updated_by=LAB,
        patient_id=new_id("pat"), biomarker=TSH,
        collection_date=NOW - timedelta(days=days_ago),
        quantity=(
            None if value is None else Quantity(value=value, unit=unit, comparator=comparator)
        ),
    )


def test_a_rising_series_is_detected():
    trend = build_lab_trend(TSH, [_lab(1.0, 60), _lab(2.0, 30), _lab(3.0, 0)])
    assert trend.direction is Direction.RISING
    assert len(trend.series) == 3
    assert trend.excluded == []


def test_a_falling_series_is_detected():
    trend = build_lab_trend(TSH, [_lab(3.0, 60), _lab(2.0, 30), _lab(1.0, 0)])
    assert trend.direction is Direction.FALLING


def test_comparator_points_stay_in_the_series_but_leave_the_arithmetic():
    # Three consecutive <0.01 are clinically meaningful; dropping them loses signal.
    labs = [
        _lab(0.01, 60, comparator="<"),
        _lab(0.01, 30, comparator="<"),
        _lab(0.01, 0, comparator="<"),
    ]
    trend = build_lab_trend(TSH, labs)
    assert len(trend.series) == 3
    assert trend.numeric_basis == []
    assert len(trend.excluded) == 3
    assert all(e.reason is ExclusionReason.LIMIT_OF_DETECTION for e in trend.excluded)
    assert trend.direction is Direction.INDETERMINATE


def test_a_mismatched_unit_is_excluded_and_named():
    # A trend that quietly adds 5.5 mmol/L to 99 mg/dL is the failure this prevents.
    trend = build_lab_trend(TSH, [_lab(2.0, 30), _lab(99.0, 0, unit="mg/dL")])
    assert any(e.reason is ExclusionReason.UNIT_MISMATCH for e in trend.excluded)


def test_an_empty_value_slot_is_excluded_as_no_value():
    trend = build_lab_trend(TSH, [_lab(2.0, 30), _lab(None, 0)])
    assert any(e.reason is ExclusionReason.NO_VALUE for e in trend.excluded)


def test_direction_needs_two_numeric_points():
    # Not a tuned threshold: two is the minimum at which a direction exists.
    trend = build_lab_trend(TSH, [_lab(2.0, 0)])
    assert trend.direction is Direction.INDETERMINATE


def test_excluded_is_a_required_field():
    assert LabTrend.model_fields["excluded"].is_required()


# --- the plan's single pass could not tell "no unit yet" from "unit is None"

def test_a_value_with_no_recorded_unit_does_not_average_into_a_series_that_has_one():
    # §9.2 admits a unit-less lab into canonical on purpose, so this input is normal.
    # The plan trended 2.0 (unit unknown) together with 99.0 mmol/L and named nothing.
    trend = build_lab_trend(TSH, [_lab(2.0, 30, unit=None), _lab(99.0, 0, unit="mmol/L")])
    assert [e.reason for e in trend.excluded] == [ExclusionReason.UNIT_MISMATCH]
    assert len(trend.numeric_basis) == 1
    assert trend.direction is Direction.INDETERMINATE


def test_a_series_with_no_units_anywhere_still_trends():
    # Nothing to mismatch against. Layer 2's MISSING_UNIT flags are what the reader sees.
    trend = build_lab_trend(TSH, [_lab(1.0, 30, unit=None), _lab(2.0, 0, unit=None)])
    assert trend.excluded == []
    assert trend.direction is Direction.RISING


def test_the_series_unit_is_the_earliest_recorded_one_not_the_earliest_point():
    # First point has no unit, so the unit comes from the second; the first is excluded.
    trend = build_lab_trend(
        TSH, [_lab(1.0, 60, unit=None), _lab(2.0, 30), _lab(3.0, 0)]
    )
    assert [e.reason for e in trend.excluded] == [ExclusionReason.UNIT_MISMATCH]
    assert len(trend.numeric_basis) == 2
    assert trend.direction is Direction.RISING


def test_every_point_appears_in_the_series_whatever_happens_to_it():
    # The §9.4 invariant: excluded from the arithmetic, never from the chart.
    labs = [
        _lab(0.01, 90, comparator="<"), _lab(None, 60), _lab(2.0, 30),
        _lab(99.0, 10, unit="mg/dL"), _lab(3.0, 0),
    ]
    trend = build_lab_trend(TSH, labs)
    assert len(trend.series) == len(labs)
    assert len(trend.numeric_basis) + len(trend.excluded) == len(labs)
