"""Lab trends (§9.4).

A comparator point is excluded from the arithmetic and not from the series. The physician
sees `<0.01, <0.01, <0.01` on the chart while the arrow abstains, which is strictly better
than three points disappearing with a note that they did.

`direction` is INDETERMINATE when and only when fewer than two numeric points remain. That
is not a tuned number but the minimum at which a direction exists at all; whether an arrow
can be trusted when half the points were excluded is a clinical judgement, not a schema
rule. Do not insert a ratio here.
"""

from enum import StrEnum

from pydantic import AwareDatetime, BaseModel

from pai3.entities.results import LabResult
from pai3.values.codeable import CodeableConcept
from pai3.values.flags import FlagSummary
from pai3.values.quantity import Quantity

MIN_POINTS_FOR_DIRECTION = 2


class Direction(StrEnum):
    RISING = "rising"
    FALLING = "falling"
    FLAT = "flat"
    INDETERMINATE = "indeterminate"


class ExclusionReason(StrEnum):
    LIMIT_OF_DETECTION = "limit_of_detection"
    NO_VALUE = "no_value"
    CODED_RESULT = "coded_result"
    UNIT_MISMATCH = "unit_mismatch"
    PATIENT_REPORTED = "patient_reported"


class TrendPoint(BaseModel):
    result_id: str
    at: AwareDatetime
    quantity: Quantity | None


class ExcludedPoint(BaseModel):
    result_id: str
    at: AwareDatetime
    quantity: Quantity | None
    reason: ExclusionReason


class LabTrend(BaseModel):
    analyte: CodeableConcept
    series: list[TrendPoint]
    numeric_basis: list[str]
    excluded: list[ExcludedPoint]
    direction: Direction
    unresolved: list[FlagSummary]


def _series_unit(ordered: list[LabResult]) -> str | None:
    """The unit the arithmetic is done in: the earliest one actually recorded.

    Decided in a pass of its own rather than while classifying, because a single pass
    cannot tell "no unit established yet" from "established as None". That conflation lets
    a value with no recorded unit — which §9.2 admits into canonical on purpose — average
    in with a value that has one, and name nothing. Returns None only when no point in the
    series recorded a unit at all; then there is nothing to mismatch against.
    """
    for result in ordered:
        q = result.quantity
        if q is not None and not q.is_bounded and q.unit is not None:
            return q.unit
    return None


def build_lab_trend(
    analyte: CodeableConcept,
    results: list[LabResult],
    unresolved: list[FlagSummary] | None = None,
) -> LabTrend:
    """Assemble a trend, naming every point that left the arithmetic.

    Mismatched units are excluded rather than converted, because conversion needs UCUM
    plus a conversion table (§10.6 records that as out of scope).
    """
    ordered = sorted(results, key=lambda r: r.collection_date)
    series_unit = _series_unit(ordered)
    series: list[TrendPoint] = []
    excluded: list[ExcludedPoint] = []
    basis: list[tuple[str, float]] = []

    for result in ordered:
        point = TrendPoint(
            result_id=result.id, at=result.collection_date, quantity=result.quantity
        )
        series.append(point)

        def drop(reason: ExclusionReason, p: TrendPoint = point) -> None:
            excluded.append(ExcludedPoint(**p.model_dump(), reason=reason))

        if result.quantity is None:
            drop(
                ExclusionReason.CODED_RESULT
                if result.coded_value is not None
                else ExclusionReason.NO_VALUE
            )
            continue
        if result.quantity.is_bounded:
            drop(ExclusionReason.LIMIT_OF_DETECTION)
            continue
        if series_unit is not None and result.quantity.unit != series_unit:
            # Covers a differing unit and a missing one alike: neither can be shown to
            # be the series unit, and a number whose unit is unknown must not be averaged.
            drop(ExclusionReason.UNIT_MISMATCH)
            continue
        basis.append((result.id, result.quantity.value))

    if len(basis) < MIN_POINTS_FOR_DIRECTION:
        direction = Direction.INDETERMINATE
    elif basis[-1][1] > basis[0][1]:
        direction = Direction.RISING
    elif basis[-1][1] < basis[0][1]:
        direction = Direction.FALLING
    else:
        direction = Direction.FLAT

    return LabTrend(
        analyte=analyte,
        series=series,
        numeric_basis=[result_id for result_id, _ in basis],
        excluded=excluded,
        direction=direction,
        unresolved=unresolved or [],
    )
