from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from pai3.ai.artifact import (
    AIClaim,
    AISummary,
    ArtifactReview,
    ClaimValue,
    Engine,
    ExtractionCandidate,
    GuardrailFailure,
    OmissionReason,
    OmittedRecord,
)
from pai3.ids import CanonicalRef, new_id

NOW = datetime(2026, 3, 12, 9, 0, tzinfo=UTC)
LAB_REF = CanonicalRef(entity_type="LabResult", entity_id=new_id("lab"), version=1)


def _summary(**over) -> AISummary:
    kwargs = {
        "id": new_id("aia"),
        "patient_id": new_id("pat"),
        "trace_id": new_id("trc"),
        "created_at": NOW,
        "inputs": [LAB_REF],
        "prompt_digest": "sha256:" + "a" * 64,
        "model_id": "llama-3.3-70b-instruct",
        "engine": Engine.OLLAMA,
        "engine_version": "0.5.1",
        "consent_ref": new_id("cons"),
        "claims": [
            AIClaim(
                text="TSH is below the reference range.",
                cites=[LAB_REF],
                values=[ClaimValue(value=0.01, unit="mIU/L", cites=LAB_REF)],
            )
        ],
        "unresolved": [],
    }
    return AISummary(**(kwargs | over))


def test_execution_has_exactly_one_legal_value():
    # §10.2: a cloud run is unrepresentable, not merely discouraged.
    assert _summary().execution == "local"
    with pytest.raises(ValidationError):
        _summary(execution="cloud")


def test_inputs_carry_versions():
    # §10.2: prompt reconstruction holds only while the named versions are unchanged.
    assert _summary().inputs[0].version == 1


def test_the_prompt_itself_is_not_a_field():
    # §10.2: storing it would duplicate PHI outside canonical governance.
    assert "prompt" not in AISummary.model_fields
    assert "prompt_digest" in AISummary.model_fields


def test_model_digest_may_be_absent():
    # Not every engine reports one; None means unknown, on §6.3's semantics.
    assert _summary().model_digest is None


def test_a_claim_must_cite_something():
    with pytest.raises(ValidationError):
        AIClaim(text="TSH is low.", cites=[], values=[])


def test_review_starts_pending():
    assert _summary().review is ArtifactReview.PENDING


def test_a_guardrail_rejection_is_a_review_state():
    artifact = _summary(
        review=ArtifactReview.REJECTED_BY_GUARDRAIL,
        guardrail_failures=[
            GuardrailFailure(check="cites_in_inputs", detail="cited lab_x was never read")
        ],
    )
    assert artifact.guardrail_failures


def test_an_empty_failure_list_is_the_passing_state():
    # §10.5: there is deliberately no guardrails_passed boolean.
    assert _summary().guardrail_failures == []
    assert "guardrails_passed" not in AISummary.model_fields


def test_omitted_records_name_their_reason():
    artifact = _summary(
        omitted=[OmittedRecord(ref=LAB_REF, reason=OmissionReason.CONTEXT_BUDGET)]
    )
    assert artifact.omitted[0].reason is OmissionReason.CONTEXT_BUDGET


def test_an_extraction_candidate_records_what_it_produced():
    # §6.19: the link runs this way because canonical never references the AI layer.
    candidate = ExtractionCandidate(
        id=new_id("aia"), patient_id=new_id("pat"), trace_id=new_id("trc"),
        created_at=NOW, inputs=[LAB_REF], prompt_digest="sha256:" + "b" * 64,
        model_id="llama-3.3-70b-instruct", engine=Engine.LLAMA_CPP,
        engine_version="b4120", consent_ref=new_id("cons"),
        proposed_entity_type="Condition",
        proposed_payload={"code": {"raw_text": "hypothyroidism"}},
    )
    assert candidate.produced == []
    accepted = candidate.model_copy(
        update={
            "produced": [
                CanonicalRef(entity_type="Condition", entity_id=new_id("cond"), version=1)
            ]
        }
    )
    assert accepted.produced[0].entity_type == "Condition"
