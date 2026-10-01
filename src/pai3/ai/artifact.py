"""The AI layer's own records.

These reference canonical by id and version. Canonical never references back (§1), which
is why `produced` lives here and not as an `artifact_ref` on provenance — the lookup
"which artifact produced this fact" is a query against this layer (§6.19).

`execution` and `consent_ref` are set by the adapter (§10.2, §10.3) and never by a
caller. The type is not what holds those invariants; the absence of a public path that
takes them as arguments is.
"""

from enum import StrEnum
from typing import Literal

from pydantic import AwareDatetime, BaseModel, Field

from pai3.ids import CanonicalRef
from pai3.values.flags import FlagSummary


class Engine(StrEnum):
    OLLAMA = "ollama"
    LLAMA_CPP = "llama_cpp"
    VLLM = "vllm"
    TRANSFORMERS = "transformers"


class ArtifactReview(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    REJECTED_BY_GUARDRAIL = "rejected_by_guardrail"
    SUPERSEDED = "superseded"


class OmissionReason(StrEnum):
    """Why a record in scope did not reach the prompt (§10.6)."""

    CONTEXT_BUDGET = "context_budget"
    OUT_OF_WINDOW = "out_of_window"
    SUPERSEDED = "superseded"
    TOO_LARGE_FOR_BUDGET = "too_large_for_budget"


class OmittedRecord(BaseModel):
    ref: CanonicalRef
    reason: OmissionReason


class GuardrailFailure(BaseModel):
    check: str
    detail: str


class ClaimValue(BaseModel):
    """A number appearing in a claim, structurally, so check 2 can compare it."""

    value: float
    unit: str | None = None
    cites: CanonicalRef


class AIClaim(BaseModel):
    """One assertion with its citations.

    The output is structured rather than prose because over prose none of §10.5's checks
    works: a number extractor that misses one produces a false pass, which is worse than
    no check at all.
    """

    text: str = Field(min_length=1)
    cites: list[CanonicalRef] = Field(min_length=1)
    values: list[ClaimValue] = Field(default_factory=list)


class AIArtifact(BaseModel):
    """What is recorded about one generation (§10.2)."""

    id: str
    patient_id: str
    trace_id: str = Field(min_length=1)
    created_at: AwareDatetime
    inputs: list[CanonicalRef]
    omitted: list[OmittedRecord] = Field(default_factory=list)
    produced: list[CanonicalRef] = Field(
        default_factory=list,
        description="What was accepted into canonical from this (§6.19)",
    )
    prompt_digest: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    model_digest: str | None = None
    engine: Engine
    engine_version: str = Field(min_length=1)
    execution: Literal["local"] = "local"
    consent_ref: str = Field(min_length=1)
    review: ArtifactReview = ArtifactReview.PENDING
    reviewed_by: str | None = None
    reviewed_at: AwareDatetime | None = None
    guardrail_failures: list[GuardrailFailure] = Field(default_factory=list)


class AISummary(AIArtifact):
    """Generated narrative as a list of cited claims."""

    claims: list[AIClaim] = Field(default_factory=list)
    unresolved: list[FlagSummary] = Field(default_factory=list)


class ExtractionCandidate(AIArtifact):
    """A proposed canonical record, awaiting a human.

    Nothing here is canonical. Acceptance creates the canonical record and records it in
    `produced`.
    """

    proposed_entity_type: str
    proposed_payload: dict
