"""The Physician Pre-Visit Brief — D8's workflow (§10.4).

Two objects with two shapes, deliberately. `PatientHeader` carries the identity the
physician needs and has no context budget: it holds everything. `narrative` is generated
from `AIPatientView`, so it cannot contain a name it never received — a type that cannot
carry identity rather than a sentence promising it will not.

`unresolved` is required with no default, so a brief that quietly dropped a flagged lab
cannot be constructed (§9.4).
"""

from datetime import date

from pydantic import AwareDatetime, BaseModel, Field

from pai3.ai.artifact import AISummary
from pai3.enums import Severity
from pai3.readmodels.timeline import TimelineEvent
from pai3.readmodels.trend import LabTrend
from pai3.values.flags import FlagSummary


class PatientHeader(BaseModel):
    """Identity, for the physician reading the brief. Never projected to a model."""

    patient_id: str
    display_name: str
    primary_mrn: str | None = None
    birth_date: date | None = None


class PreVisitBrief(BaseModel):
    header: PatientHeader
    generated_at: AwareDatetime
    unresolved: list[FlagSummary]
    active_conditions: list[str] = Field(default_factory=list)
    active_symptoms: list[str] = Field(default_factory=list)
    active_medications: list[str] = Field(default_factory=list)
    active_supplements: list[str] = Field(default_factory=list)
    allergies: list[str] = Field(default_factory=list)
    recent_vitals: list[str] = Field(default_factory=list)
    trends: list[LabTrend] = Field(default_factory=list)
    timeline: list[TimelineEvent] = Field(default_factory=list)
    narrative: AISummary | None = None
    narrative_withheld_reason: str | None = Field(
        default=None,
        description="Why no narrative: a refused generation, or a guardrail rejection",
    )

    @property
    def has_blocking_flags(self) -> bool:
        return any(f.severity is Severity.BLOCKING for f in self.unresolved)
