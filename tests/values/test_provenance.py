from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from pai3.enums import ProvenanceOrigin
from pai3.ids import CanonicalRef, new_id
from pai3.values.actor import Actor, ActorKind
from pai3.values.provenance import Provenance, resolve_provenance

NOW = datetime(2026, 3, 12, 9, 0, tzinfo=UTC)
CLINICIAN = Actor(kind=ActorKind.HUMAN, ref=new_id("prov"), label="Dr A. Reyes")
PIPELINE = Actor(kind=ActorKind.PIPELINE, ref="emr-import", label="emr-import")


def _ref(version: int = 1) -> CanonicalRef:
    return CanonicalRef(entity_type="Condition", entity_id=new_id("cond"), version=version)


def test_human_origin_needs_neither_refs_nor_parents():
    prov = Provenance(origin=ProvenanceOrigin.HUMAN, asserted_by=CLINICIAN, asserted_at=NOW)
    assert prov.depth == 0


def test_ai_extraction_requires_a_source_ref():
    # Extraction came from a document; without the pointer there is no evidence.
    with pytest.raises(ValidationError, match="source_refs"):
        Provenance(
            origin=ProvenanceOrigin.AI_EXTRACTION, asserted_by=CLINICIAN, asserted_at=NOW
        )


def test_ai_extraction_with_a_source_ref_is_valid():
    prov = Provenance(
        origin=ProvenanceOrigin.AI_EXTRACTION,
        asserted_by=CLINICIAN,
        asserted_at=NOW,
        source_refs=[new_id("sref")],
        extraction_confidence=0.82,
    )
    assert prov.depth == 0


def test_ai_inference_requires_a_parent():
    with pytest.raises(ValidationError, match="derived_from"):
        Provenance(
            origin=ProvenanceOrigin.AI_INFERENCE, asserted_by=CLINICIAN, asserted_at=NOW
        )


def test_ai_inference_is_capped_at_depth_one():
    # Spec §6.19: AI may reason from documents and from first-generation facts,
    # never from its own inferences. Without the cap the chain compounds.
    with pytest.raises(ValidationError, match="depth"):
        Provenance(
            origin=ProvenanceOrigin.AI_INFERENCE,
            asserted_by=CLINICIAN,
            asserted_at=NOW,
            derived_from=[_ref()],
            depth=2,
        )


def test_ai_inference_at_depth_one_is_valid():
    prov = Provenance(
        origin=ProvenanceOrigin.AI_INFERENCE,
        asserted_by=CLINICIAN,
        asserted_at=NOW,
        derived_from=[_ref()],
        depth=1,
    )
    assert prov.depth == 1


def test_depth_zero_requires_no_parents():
    with pytest.raises(ValidationError, match="depth"):
        Provenance(
            origin=ProvenanceOrigin.AI_INFERENCE,
            asserted_by=CLINICIAN,
            asserted_at=NOW,
            derived_from=[_ref()],
            depth=0,
        )


def test_parents_require_a_nonzero_depth():
    with pytest.raises(ValidationError, match="depth"):
        Provenance(
            origin=ProvenanceOrigin.HUMAN,
            asserted_by=CLINICIAN,
            asserted_at=NOW,
            derived_from=[_ref()],
            depth=0,
        )


def test_system_derived_asserts_nothing_clinical():
    prov = Provenance(
        origin=ProvenanceOrigin.SYSTEM_DERIVED, asserted_by=PIPELINE, asserted_at=NOW
    )
    assert not prov.is_clinical_assertion


def test_human_and_extraction_are_clinical_assertions():
    for origin, extra in (
        (ProvenanceOrigin.HUMAN, {}),
        (ProvenanceOrigin.AI_EXTRACTION, {"source_refs": [new_id("sref")]}),
    ):
        prov = Provenance(
            origin=origin, asserted_by=CLINICIAN, asserted_at=NOW, **extra
        )
        assert prov.is_clinical_assertion


def test_confidence_outside_zero_to_one_is_refused():
    with pytest.raises(ValidationError):
        Provenance(
            origin=ProvenanceOrigin.AI_EXTRACTION,
            asserted_by=CLINICIAN,
            asserted_at=NOW,
            source_refs=[new_id("sref")],
            extraction_confidence=1.4,
        )


def test_resolve_provenance_prefers_the_field_override():
    record = Provenance(origin=ProvenanceOrigin.HUMAN, asserted_by=CLINICIAN, asserted_at=NOW)
    field = Provenance(
        origin=ProvenanceOrigin.SOURCE_SYSTEM, asserted_by=PIPELINE, asserted_at=NOW
    )
    assert resolve_provenance("dose", record, {"dose": field}).origin is (
        ProvenanceOrigin.SOURCE_SYSTEM
    )


def test_resolve_provenance_falls_back_to_the_record():
    record = Provenance(origin=ProvenanceOrigin.HUMAN, asserted_by=CLINICIAN, asserted_at=NOW)
    assert resolve_provenance("dose", record, {}).origin is ProvenanceOrigin.HUMAN
