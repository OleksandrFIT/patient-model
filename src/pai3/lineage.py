"""Depth and retraction, the two halves of §6.19 that need to see the parents.

`depth` is stored rather than derived on read, and that does not contradict §6.13's
refusal to store derived values: it is computed once from parents named *by version*,
and a named version never changes, so it cannot go stale. The gain is that "everything
deeper than one, pending review" is a single filter rather than a recursive walk.
"""

from datetime import datetime

from pai3.entities.infrastructure import DataQualityFlag, FlagTarget
from pai3.enums import FlagCode, ProvenanceOrigin, Severity
from pai3.ids import CanonicalRef, new_id
from pai3.values.actor import Actor
from pai3.values.provenance import AI_INFERENCE_MAX_DEPTH, Provenance


class DepthTooGreat(ValueError):
    """Raised when an ai_inference would exceed the §6.19 cap."""


def compute_depth(
    parents: list[Provenance],
    origin: ProvenanceOrigin = ProvenanceOrigin.HUMAN,
) -> int:
    """`0` with no parents, otherwise one past the deepest parent.

    The cap applies only to AI inference. A clinician reading the chart and asserting
    something from it is `human`, and no ceiling applies to a person's judgement.
    """
    if not parents:
        return 0
    depth = 1 + max(p.depth for p in parents)
    if origin is ProvenanceOrigin.AI_INFERENCE and depth > AI_INFERENCE_MAX_DEPTH:
        raise DepthTooGreat(
            f"ai_inference would reach depth {depth}; the cap is {AI_INFERENCE_MAX_DEPTH}. "
            "AI may reason from documents and first-generation facts, not from inferences."
        )
    return depth


def retraction_cascade(
    retracted_id: str,
    children: list[tuple[str, str, list[CanonicalRef]]],
    patient_id: str,
    actor: Actor,
    now: datetime,
) -> list[DataQualityFlag]:
    """Flag every record that reasoned from a record just marked entered_in_error.

    `children` is `(entity_type, entity_id, derived_from)` for the candidate records —
    passed in rather than queried, so this stays a pure function the caller can test.

    Severity is BLOCKING on §9.1's meaning: the derived fact may still be true, but its
    basis is gone, so no autonomous conclusion may rest on it until a human has looked.

    Single-level by design: retracting A flags B, which was derived from A, but not C,
    which was derived from B. A caller that wants the transitive closure re-runs this for
    each newly flagged record. That is tolerable because §6.19 caps `ai_inference` at
    depth 1, so a three-link chain needs a human assertion at each step.
    """
    flags: list[DataQualityFlag] = []
    for entity_type, entity_id, parents in children:
        if not any(ref.entity_id == retracted_id for ref in parents):
            continue
        flags.append(
            DataQualityFlag(
                id=new_id("flag"),
                provenance=Provenance(
                    origin=ProvenanceOrigin.SYSTEM_DERIVED,
                    asserted_by=actor,
                    asserted_at=now,
                ),
                created_at=now,
                updated_at=now,
                updated_by=actor,
                patient_id=patient_id,
                code=FlagCode.PARENT_RETRACTED,
                severity=Severity.BLOCKING,
                message=(
                    f"{entity_type} {entity_id} was derived from {retracted_id}, "
                    "which has been marked entered_in_error"
                ),
                targets=[FlagTarget(entity_type=entity_type, entity_id=entity_id)],
            )
        )
    return flags
