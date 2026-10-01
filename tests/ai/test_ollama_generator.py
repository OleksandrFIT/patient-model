"""The real generator, against a model actually running on this machine.

Skipped when ollama is not reachable, so the suite stays green on a machine without it. These
are the only tests in the repository that depend on something outside the process, and they
are worth it: every defect in `OllamaGenerator` found so far was found by running it, not by
reasoning about it.
"""

import json
import urllib.error
import urllib.request
from datetime import UTC, datetime

import pytest

from pai3.ai.artifact import Engine
from pai3.ai.generators import (
    CLAIM_SCHEMA,
    GenerationContext,
    OllamaGenerator,
    OllamaUnavailable,
    StubGenerator,
    resolve_citation,
)
from pai3.ai.projection import AIPatientView
from pai3.entities.results import LabResult
from pai3.enums import ProvenanceOrigin
from pai3.ids import new_id
from pai3.readmodels.trend import build_lab_trend
from pai3.values.actor import Actor, ActorKind
from pai3.values.codeable import CodeableConcept
from pai3.values.provenance import Provenance
from pai3.values.quantity import Quantity, ReferenceRange

MODEL = "qwen2.5:7b"
NOW = datetime(2026, 3, 12, 9, 0, tzinfo=UTC)
LAB_ACTOR = Actor(kind=ActorKind.SYSTEM, ref="lab", label="lab")
PROV = Provenance(
    origin=ProvenanceOrigin.SOURCE_SYSTEM, asserted_by=LAB_ACTOR, asserted_at=NOW
)


def _ollama_available() -> bool:
    try:
        with urllib.request.urlopen("http://localhost:11434/api/version", timeout=3) as r:
            json.loads(r.read())
    except (urllib.error.URLError, TimeoutError, OSError):
        return False
    try:
        req = urllib.request.Request(
            "http://localhost:11434/api/show",
            data=json.dumps({"model": MODEL}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=5):
            return True
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


needs_ollama = pytest.mark.skipif(
    not _ollama_available(), reason=f"ollama with {MODEL} is not reachable on localhost"
)


def _lab(value: float | None, analyte: str = "TSH") -> LabResult:
    return LabResult(
        id=new_id("lab"), provenance=PROV, created_at=NOW, updated_at=NOW,
        updated_by=LAB_ACTOR, patient_id=new_id("pat"),
        biomarker=CodeableConcept(raw_text=analyte, system="LOINC", code="3016-3"),
        collection_date=NOW,
        quantity=None if value is None else Quantity(value=value, unit="mIU/L"),
        reference_range=ReferenceRange(low=0.4, high=4.0),
    )


def _ctx(labs: list[LabResult]) -> GenerationContext:
    return GenerationContext(
        view=AIPatientView(patient_id=new_id("pat"), age_years=47, sex="female"),
        labs=labs,
        trends=[build_lab_trend(labs[0].biomarker, labs)] if labs else [],
        unresolved=[],
    )


# ------------------------------------------------------------ no model needed

def test_the_schema_requires_text_and_citations():
    item = CLAIM_SCHEMA["properties"]["claims"]["items"]
    assert set(item["required"]) == {"text", "cites"}
    assert "values" in item["properties"]


def test_the_prompt_labels_records_by_index_and_never_shows_an_id():
    labs = [_lab(5.6), _lab(None, "glucose, fasting")]
    rendered = _ctx(labs).render()
    prompt = rendered.text

    assert "[1]" in prompt
    assert "[2]" in prompt
    # The reason indices exist: an id the model never sees is an id it cannot mangle.
    for lab in labs:
        assert lab.id not in prompt
    # The map resolves to the real records, in the order the prompt listed them.
    assert [rendered.by_index[k].entity_id for k in ("1", "2")] == [labs[0].id, labs[1].id]
    assert "VALUE ABSENT" in prompt
    # Assert the instruction is there, not its exact phrasing: a test pinned to wording
    # breaks when the wording is improved, which teaches nothing.
    lowered = prompt.lower()
    assert "`values`" in lowered
    assert "rejected" in lowered


def test_an_index_the_prompt_never_offered_cannot_resolve():
    """The `[9]` case. It must fail exactly as a wrong id did, or indices would trade a
    fabrication the guardrails catch for one they do not."""
    labs = [_lab(3.8), _lab(5.6)]
    by_index = _ctx(labs).render().by_index

    assert resolve_citation("[1]", by_index).entity_id == labs[0].id
    assert resolve_citation("2", by_index).entity_id == labs[1].id
    assert resolve_citation(" [2] ", by_index).entity_id == labs[1].id

    known = {lab.id for lab in labs}
    for fabricated in ("[9]", "9", "lab_01ARZ3NDEKTSV4RRFFQ69G5FAV", "TSH", "[1,2]", ""):
        assert resolve_citation(fabricated, by_index).entity_id not in known


def test_the_prompt_carries_no_identity():
    # §10.4 end to end: whatever reaches the model cannot contain a name or an MRN.
    # .text, not the tuple: `"Okafor" not in RenderedPrompt(...)` compares against the
    # tuple's elements and passes whatever the prompt says.
    prompt = _ctx([_lab(5.6)]).render().text
    for forbidden in ("Okafor", "Dana", "MRN"):
        assert forbidden not in prompt


def test_the_stub_declares_itself():
    stub = StubGenerator()
    assert stub.engine is Engine.STUB
    assert stub.model_id.startswith("stub:")
    assert stub.model_digest is None


def test_an_unreachable_host_raises_rather_than_returning_nothing():
    with pytest.raises(OllamaUnavailable):
        OllamaGenerator(MODEL, host="http://localhost:1")


# -------------------------------------------------------------- needs a model

@needs_ollama
def test_a_real_model_produces_citable_claims():
    gen = OllamaGenerator(MODEL)
    assert gen.engine is Engine.OLLAMA
    assert gen.engine_version and gen.engine_version != "unknown"

    labs = [_lab(3.8), _lab(5.6)]
    generated = gen.generate(_ctx(labs))
    assert generated.prompt
    assert generated.claims, "the model returned nothing parseable"
    known = {lab.id for lab in labs}
    for claim in generated.claims:
        assert claim.cites
        for ref in claim.cites:
            # A hallucinated id is passed through on purpose so guardrail 1 catches it;
            # here we only assert the parser produced refs at all.
            assert ref.entity_id
        assert any(ref.entity_id in known for ref in claim.cites)


@needs_ollama
def test_a_real_model_is_told_not_to_value_an_absent_result():
    # Not an assertion about the model's obedience -- it is not reliably obedient, which is
    # the point of guardrail 3. This pins that the instruction reaches it.
    gen = OllamaGenerator(MODEL)
    ctx = _ctx([_lab(None, "glucose, fasting")])
    assert "VALUE ABSENT" in ctx.render().text
    generated = gen.generate(ctx)
    assert generated.prompt == ctx.render().text


@needs_ollama
def test_the_digest_is_none_when_the_runtime_does_not_report_one():
    # ollama's /api/show exposes quantisation and architecture but no weight digest, so None
    # is the honest answer and §6.3's semantics apply: None means unknown, not zero.
    gen = OllamaGenerator(MODEL)
    assert gen.model_digest is None or gen.model_digest.startswith("sha256")
