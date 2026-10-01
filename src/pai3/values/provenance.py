"""Where a value came from.

Provenance is a property of a value; AuditEvent is a stream of events over a record
(§6.3). Conflating the two is the most common failure in models of this kind.

`source_refs` terminates in a document, so `derived_from` exists to say "this fact
came from that canonical record" — without which a second-generation fact is
indistinguishable from a first-generation one and an extraction error grows
derivatives invisibly (§6.19).
"""

from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from pai3.enums import ProvenanceOrigin
from pai3.ids import CanonicalRef
from pai3.values.actor import Actor

AI_INFERENCE_MAX_DEPTH = 1
"""§6.19: AI reasons from documents and first-generation facts, not from inferences."""

_CLINICAL_ASSERTIONS = {
    ProvenanceOrigin.HUMAN,
    ProvenanceOrigin.SOURCE_SYSTEM,
    ProvenanceOrigin.AI_EXTRACTION,
    ProvenanceOrigin.AI_INFERENCE,
}


class Provenance(BaseModel):
    origin: ProvenanceOrigin
    asserted_by: Actor
    asserted_at: datetime
    imported_at: datetime | None = None
    source_refs: list[str] = Field(
        default_factory=list, description="SourceReference ids — document, page, span"
    )
    derived_from: list[CanonicalRef] = Field(
        default_factory=list, description="Canonical records this was reasoned from"
    )
    depth: int = Field(default=0, ge=0, description="0 = straight from a document")
    extraction_confidence: float | None = Field(default=None, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _extraction_cites_a_document(self) -> "Provenance":
        if self.origin is ProvenanceOrigin.AI_EXTRACTION and not self.source_refs:
            raise ValueError("ai_extraction requires a non-empty source_refs")
        return self

    @model_validator(mode="after")
    def _inference_names_its_parents(self) -> "Provenance":
        if self.origin is ProvenanceOrigin.AI_INFERENCE and not self.derived_from:
            raise ValueError("ai_inference requires a non-empty derived_from")
        return self

    @model_validator(mode="after")
    def _depth_agrees_with_parents(self) -> "Provenance":
        if bool(self.derived_from) != (self.depth > 0):
            raise ValueError(
                "depth must be 0 exactly when derived_from is empty; "
                f"got depth={self.depth} with {len(self.derived_from)} parents"
            )
        return self

    @model_validator(mode="after")
    def _inference_respects_the_cap(self) -> "Provenance":
        if (
            self.origin is ProvenanceOrigin.AI_INFERENCE
            and self.depth > AI_INFERENCE_MAX_DEPTH
        ):
            raise ValueError(
                f"ai_inference is capped at depth {AI_INFERENCE_MAX_DEPTH}; got {self.depth}"
            )
        return self

    @property
    def is_clinical_assertion(self) -> bool:
        """False for SYSTEM_DERIVED, which is pipeline bookkeeping (§6.19)."""
        return self.origin in _CLINICAL_ASSERTIONS


def resolve_provenance(
    field_name: str, record: Provenance, overrides: dict[str, Provenance]
) -> Provenance:
    """Provenance for one field: the override if the whitelist carries one (§6.2).

    The whitelist is per entity class and deliberately short — `dose` and `status` on
    Medication, `quantity` on LabResult, `clinical_status` on Condition. A vague rule
    grows the map to twenty fields within a week.
    """
    return overrides.get(field_name, record)
