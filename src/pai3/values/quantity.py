"""A measured value.

`value` is required here so that `quantity is not None` implies a value exists, which
is what lets LabResult carry an empty slot for an unresolved conflict (§9.3) without
admitting a half-filled one.
"""

from typing import Literal

from pydantic import BaseModel, model_validator

Comparator = Literal["<", ">", "<=", ">="]


class Quantity(BaseModel):
    value: float
    unit: str | None = None
    ucum_code: str | None = None
    comparator: Comparator | None = None

    @property
    def is_bounded(self) -> bool:
        """True when this is a limit-of-detection result rather than a point.

        A bounded value cannot be averaged (§9.4) and cannot be compared to a
        reference range as though it were measured (§9.5).
        """
        return self.comparator is not None


class ReferenceRange(BaseModel):
    """The range as the performing lab reported it.

    `low` is optional because many analytes have no meaningful lower bound, and §9.5
    depends on being able to tell "low is zero or absent" from "low is 0.4".
    """

    low: float | None = None
    high: float | None = None
    source_label: str | None = None

    @model_validator(mode="after")
    def _interval_is_not_inverted(self) -> "ReferenceRange":
        if self.low is not None and self.high is not None and self.low > self.high:
            raise ValueError(f"inverted reference range: {self.low} > {self.high}")
        return self
