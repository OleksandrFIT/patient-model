"""DiagnosticReport, LabResult and VitalSign.

Labs and vitals stay separate (§6.6) because their validation severities genuinely
differ — a lab without a unit is a layer-2 flag, a blood pressure without a cuff size is
an acceptable missing value — and merging would make the validator branch on category to
decide that. DiagnosticReport and VitalSign arrive in Phase 2.
"""

from typing import ClassVar

from pydantic import AwareDatetime, Field, model_validator

from pai3.base import ClinicalRecord
from pai3.enums import Interpretation
from pai3.interpretation import interpret
from pai3.values.codeable import CodeableConcept
from pai3.values.quantity import Quantity, ReferenceRange


class LabResult(ClinicalRecord):
    """One analyte.

    The value lives in one of two parallel slots rather than a union, because a
    discriminated union would require a literal tag field on both `Quantity` and
    `CodeableConcept`, which six other entities share (§6.9).
    """

    FIELD_PROVENANCE_WHITELIST: ClassVar[frozenset[str]] = frozenset({"quantity"})

    biomarker: CodeableConcept
    collection_date: AwareDatetime
    quantity: Quantity | None = None
    coded_value: CodeableConcept | None = Field(
        default=None, description="positive, negative, trace"
    )
    reference_range: ReferenceRange | None = None
    reported_interpretation: CodeableConcept | None = Field(
        default=None, description="The lab's own H / L / HH / A — a source fact (§9.5)"
    )
    specimen: str | None = None
    performing_lab: str | None = None
    ordering_provider_id: str | None = None
    report_id: str | None = Field(default=None, description="DiagnosticReport id (§6.8)")

    @model_validator(mode="after")
    def _at_most_one_value_slot(self) -> "LabResult":
        if self.quantity is not None and self.coded_value is not None:
            raise ValueError("at most one of quantity and coded_value may be populated")
        return self

    @property
    def has_value(self) -> bool:
        """False for an unresolved conflict or a failed extraction — the flag says which."""
        return self.quantity is not None or self.coded_value is not None

    @property
    def computed_interpretation(self) -> Interpretation:
        """Ours, derived from the stored range (§9.5). Never overwrites the lab's."""
        if self.quantity is None:
            return Interpretation.INDETERMINATE
        return interpret(self.quantity, self.reference_range)

    @property
    def display_interpretation(self) -> tuple[str, str] | None:
        """What a read-model shows, and where it came from.

        The lab's reading wins when present: ours depends on which reference range we
        stored, which is exactly what a disagreement puts in doubt (§9.5).
        """
        if self.reported_interpretation is not None:
            return (self.reported_interpretation.raw_text, "reported")
        computed = self.computed_interpretation
        if computed is Interpretation.INDETERMINATE:
            return None
        return (computed.value, "computed")
