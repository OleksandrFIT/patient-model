"""Whether a result is low, normal or high — derived, never stored (§9.5).

A comparator makes a value an interval, so the comparison is decidable only when the
interval lies entirely on one side of a boundary. Where it is not, the answer is
INDETERMINATE: a value, not a defect. The assay output is correct and only the derived
interpretation is unavailable, so raising a flag would fill the review queue with
items nobody can resolve.

The lab's own reading is stored separately as `LabResult.reported_interpretation` and
is never overwritten by this computation — the lab vouched for its "H", which makes it
a source fact, and replacing it with ours is no better than letting AI rewrite
canonical (§1).
"""

from pai3.enums import Interpretation
from pai3.values.codeable import CodeableConcept
from pai3.values.quantity import Quantity, ReferenceRange

_REPORTED_TOKENS: dict[str, Interpretation] = {
    "l": Interpretation.LOW,
    "ll": Interpretation.LOW,
    "low": Interpretation.LOW,
    "n": Interpretation.NORMAL,
    "normal": Interpretation.NORMAL,
    "h": Interpretation.HIGH,
    "hh": Interpretation.HIGH,
    "high": Interpretation.HIGH,
}


def interpret(quantity: Quantity, reference: ReferenceRange | None) -> Interpretation:
    """Apply §9.5's decision table.

    Returns INDETERMINATE whenever the comparison is not sound, including when there
    is no usable range at all.

    Every bound comparison sits *inside* its own `is not None` guard. Computing the
    comparison first and guarding afterwards raises TypeError on a half-open range,
    which is the common shape: hs-CRP has no lower bound, and many analytes no upper.
    """
    if reference is None or (reference.low is None and reference.high is None):
        return Interpretation.INDETERMINATE

    low, high = reference.low, reference.high
    x = quantity.value

    # Row 1 — a point value compares ordinarily.
    if quantity.comparator is None:
        if low is not None and x < low:
            return Interpretation.LOW
        if high is not None and x > high:
            return Interpretation.HIGH
        return Interpretation.NORMAL

    # Rows 2-3 — the interval lies below x.
    if quantity.comparator in ("<", "<="):
        if low is not None:
            # "<x" admits x itself as an upper exclusive bound, so x <= low suffices.
            # "<=x" includes x, so a verdict of LOW needs x strictly under low.
            below_low = (x <= low) if quantity.comparator == "<" else (x < low)
            if below_low:
                return Interpretation.LOW
        # Row 3 — with no meaningful lower bound the interval is contained in range.
        if (low is None or low == 0.0) and high is not None and x <= high:
            return Interpretation.NORMAL
        return Interpretation.INDETERMINATE

    # Row 4 — the interval lies above x.
    if high is not None:
        above_high = (x >= high) if quantity.comparator == ">" else (x > high)
        if above_high:
            return Interpretation.HIGH

    # Row 5 — the interval crosses a boundary, or extends past an absent one.
    return Interpretation.INDETERMINATE


def interpretation_disagrees(
    reported: CodeableConcept | None, computed: Interpretation
) -> bool:
    """True when the lab's own reading and ours conflict (§9.5).

    A disagreement almost always means the reference range stored here is not the one
    the lab used, which makes every other interpretation against that range suspect —
    hence FlagCode.INTERPRETATION_DISAGREES_WITH_RANGE.

    An unrecognised token returns False: we cannot claim a conflict with something we
    failed to understand.
    """
    if reported is None or computed is Interpretation.INDETERMINATE:
        return False
    mapped = _REPORTED_TOKENS.get(reported.raw_text.strip().lower())
    if mapped is None:
        return False
    return mapped is not computed
